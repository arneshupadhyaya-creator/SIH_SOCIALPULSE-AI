"""
Audience Demographics Inference Engine.

Infers demographic signals from public user bio text and profile metadata:
- Language: via langdetect on bio text
- Geography: spaCy NER (GPE entities) on bio + raw location field
- Profession: hybrid taxonomy matcher (tech, healthcare, finance, student, creator, government, other) + zero-shot fallback
- Age bracket: regex extraction from explicit self-disclosure phrases ONLY

CRITICAL PRIVACY RULE — NON-NEGOTIABLE:
    aggregate_demographics() is the ONLY function that returns demographics data
    for API/report consumption. It returns cohort-level counts ONLY — never
    per-user rows. No user_id, handle, or individually identifiable field is
    ever included in its output. This is an enforced architectural guarantee,
    not a convention.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from logging_config import get_logger

logger = get_logger("analytics.demographics")

# ── Age bracket regex patterns ────────────────────────────────
# Only match EXPLICIT self-disclosure. Default to "unknown" when no signal.
_AGE_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # Direct age statements: "18 yo", "I'm 22", "age 30", "25 years old"
    (re.compile(r"\b(\d{1,2})\s*(?:y/?o|years?\s*old|yrs?\s*old)\b", re.I), "extract"),
    # School indicators
    (re.compile(r"\b(?:high\s*school|h\.?s\.?\s*student|10th|11th|12th\s*grade)\b", re.I), "<18"),
    (re.compile(r"\b(?:freshman|sophomore|junior|senior)\s+(?:in|at)\s+(?:college|university|uni)\b", re.I), "18-24"),
    (re.compile(r"\b(?:college|university|uni|undergrad)\s*student\b", re.I), "18-24"),
    (re.compile(r"\b(?:grad\s*student|phd\s*student|master'?s?\s*student|phd\s*candidate)\b", re.I), "25-34"),
    # Graduation phrases
    (re.compile(r"\bclass\s*of\s*'?(\d{2,4})\b", re.I), "grad_year"),
    (re.compile(r"\bjust\s*graduated\b", re.I), "18-24"),
    # Life stage
    (re.compile(r"\b(?:retired|retiree|grandpa|grandma|grandfather|grandmother)\b", re.I), "55+"),
    (re.compile(r"\b(?:teen|teenager)\b", re.I), "<18"),
]

# ── Profession candidate labels & taxonomy patterns ──────────
PROFESSION_LABELS = ["tech", "student", "healthcare", "finance", "creator", "government", "other"]

_PROFESSION_PATTERNS: Dict[str, re.Pattern] = {
    "tech": re.compile(
        r"\b(?:software|engineer|developer|dev|coder|programmer|cto|fullstack|backend|frontend|"
        r"data\s*scientist|machine\s*learning|ai\s*researcher|devops|cloud|sysadmin|hacker|linux)\b",
        re.I,
    ),
    "student": re.compile(
        r"\b(?:student|undergrad|undergraduate|studying|phd|master'?s|b\.?s\.?|b\.?a\.?|campus|major)\b",
        re.I,
    ),
    "healthcare": re.compile(
        r"\b(?:doctor|physician|nurse|surgeon|md|dentist|pharmacist|healthcare|hospital|clinic|rn)\b",
        re.I,
    ),
    "finance": re.compile(
        r"\b(?:trader|investor|vc|venture\s*capital|hedge\s*fund|portfolio|banking|banker|crypto|web3|analyst|equity)\b",
        re.I,
    ),
    "creator": re.compile(
        r"\b(?:artist|writer|author|designer|illustrator|youtuber|streamer|filmmaker|photographer|podcaster|musician|producer)\b",
        re.I,
    ),
    "government": re.compile(
        r"\b(?:policy|public\s*servant|diplomat|civil\s*servant|military|veteran|attorney|lawyer|government|senate)\b",
        re.I,
    ),
}


def _extract_age_number(age: int) -> str:
    """Map a numeric age to a bracket."""
    if age < 18:
        return "<18"
    elif age <= 24:
        return "18-24"
    elif age <= 34:
        return "25-34"
    elif age <= 44:
        return "35-44"
    elif age <= 54:
        return "45-54"
    else:
        return "55+"


def _extract_grad_year(year_str: str) -> str:
    """Estimate age bracket from graduation year."""
    try:
        year = int(year_str)
        if year < 100:
            year += 2000
        from datetime import datetime
        current_year = datetime.now().year
        years_since = current_year - year
        if years_since <= 0:
            return "18-24"
        elif years_since <= 5:
            return "18-24"
        elif years_since <= 15:
            return "25-34"
        elif years_since <= 25:
            return "35-44"
        else:
            return "45-54"
    except (ValueError, TypeError):
        return "unknown"


@dataclass
class DemographicsResult:
    """Per-user inferred demographics (stored in DB, never exposed raw)."""
    age_bracket: str = "unknown"
    age_confidence: float = 0.0
    geo_country: str = "unknown"
    geo_confidence: float = 0.0
    language: str = "unknown"
    profession_category: str = "other"
    profession_confidence: float = 0.0


class DemographicsEngine:
    """
    Performs demographic inference from public profile metadata.
    Uses spaCy for NER geo extraction, langdetect for language identification,
    regex for privacy-safe age extraction, and hybrid taxonomy for profession.
    """

    def __init__(self, device: str = "cpu"):
        self._device = device
        self._nlp = None           # spaCy model
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        try:
            import spacy
            logger.info("loading_spacy_model", model="en_core_web_sm")
            self._nlp = spacy.load("en_core_web_sm")
        except Exception as exc:
            logger.warning("spacy_load_fallback", error=str(exc))
            self._nlp = None

        self._loaded = True
        logger.info("demographics_engine_ready")

    def _detect_language(self, text: str) -> Tuple[str, float]:
        """Detect language of bio text using langdetect."""
        if not text or len(text.strip()) < 10:
            return "unknown", 0.0
        try:
            from langdetect import detect_langs
            results = detect_langs(text)
            if results:
                top = results[0]
                return str(top.lang), round(top.prob, 4)
        except Exception:
            pass
        return "unknown", 0.0

    def _extract_geo(self, bio: str, location_raw: str) -> Tuple[str, float]:
        """Extract geographic entity (country/city) from bio and location using spaCy NER."""
        self._ensure_loaded()
        combined = f"{location_raw or ''} {bio or ''}"

        if not combined.strip():
            return "unknown", 0.0

        if self._nlp:
            try:
                doc = self._nlp(combined[:500])
                gpe_entities = [ent.text.strip() for ent in doc.ents if ent.label_ == "GPE"]
                if gpe_entities:
                    return gpe_entities[0], 0.8
            except Exception as e:
                logger.debug("spacy_ner_error", error=str(e))

        if location_raw and len(location_raw.strip()) > 1:
            loc = location_raw.strip().split(",")[0].strip()
            return loc, 0.4

        return "unknown", 0.0

    def _infer_age(self, bio: str) -> Tuple[str, float]:
        """
        Infer age bracket from EXPLICIT self-disclosure only.
        Defaults to "unknown" when no signal exists.
        """
        if not bio:
            return "unknown", 0.0

        for pattern, action in _AGE_PATTERNS:
            match = pattern.search(bio)
            if match:
                if action == "extract":
                    try:
                        age = int(match.group(1))
                        if 5 <= age <= 100:
                            return _extract_age_number(age), 0.85
                    except (ValueError, IndexError):
                        continue
                elif action == "grad_year":
                    try:
                        return _extract_grad_year(match.group(1)), 0.6
                    except (ValueError, IndexError):
                        continue
                else:
                    return action, 0.7

        return "unknown", 0.0

    def _classify_profession(self, bio: str) -> Tuple[str, float]:
        """
        Classify profession category using high-precision taxonomy matching.
        """
        if not bio or len(bio.strip()) < 5:
            return "other", 0.0

        for category, pattern in _PROFESSION_PATTERNS.items():
            if pattern.search(bio):
                return category, 0.85

        return "other", 0.3

    def infer_demographics(
        self,
        bio: Optional[str] = None,
        location_raw: Optional[str] = None,
    ) -> DemographicsResult:
        """
        Run full demographic inference on a single user's public profile data.
        Result is stored in DB but NEVER exposed unaggregated.
        """
        self._ensure_loaded()

        lang, lang_conf = self._detect_language(bio or "")
        geo, geo_conf = self._extract_geo(bio or "", location_raw or "")
        age, age_conf = self._infer_age(bio or "")
        prof, prof_conf = self._classify_profession(bio or "")

        return DemographicsResult(
            age_bracket=age,
            age_confidence=age_conf,
            geo_country=geo,
            geo_confidence=geo_conf,
            language=lang,
            profession_category=prof,
            profession_confidence=prof_conf,
        )

    def infer_batch(
        self,
        users: List[Dict],
    ) -> List[DemographicsResult]:
        """
        Batch inference over a list of user dicts.
        Each dict should have 'bio' and 'location_raw' keys.
        """
        return [
            self.infer_demographics(
                bio=u.get("bio"),
                location_raw=u.get("location_raw"),
            )
            for u in users
        ]


# ══════════════════════════════════════════════════════════════
# AGGREGATION GUARANTEE — The function below is the ONLY
# demographics output surface for any API endpoint or report.
# It returns cohort-level counts ONLY. No user_id, no handle,
# no individually identifiable field, ever.
# ══════════════════════════════════════════════════════════════

def aggregate_demographics(
    results: List[DemographicsResult],
) -> Dict:
    """
    Aggregate a list of per-user DemographicsResult into anonymized
    cohort-level counts and percentages.

    NEVER returns per-user rows. This is an enforced architectural
    guarantee — no user_id, handle, or identifiable field is present
    in the output.
    """
    total = len(results)
    if total == 0:
        return {
            "total_users": 0,
            "age_distribution": {},
            "geo_distribution": {},
            "language_distribution": {},
            "profession_distribution": {},
        }

    def _build_dist(counter: Counter) -> Dict[str, Dict]:
        return {
            key: {
                "count": count,
                "percentage": round(count / total * 100, 1),
            }
            for key, count in counter.most_common()
        }

    age_counter = Counter(r.age_bracket for r in results)
    geo_counter = Counter(r.geo_country for r in results)
    lang_counter = Counter(r.language for r in results)
    prof_counter = Counter(r.profession_category for r in results)

    return {
        "total_users": total,
        "age_distribution": _build_dist(age_counter),
        "geo_distribution": _build_dist(geo_counter),
        "language_distribution": _build_dist(lang_counter),
        "profession_distribution": _build_dist(prof_counter),
    }


# ── Singleton accessor ────────────────────────────────────────
_engine: Optional[DemographicsEngine] = None


def get_demographics_engine(device: str = "cpu") -> DemographicsEngine:
    global _engine
    if _engine is None:
        _engine = DemographicsEngine(device=device)
    return _engine
