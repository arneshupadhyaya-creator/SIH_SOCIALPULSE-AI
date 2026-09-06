"""
Sentiment & Emotion Analysis Engine — Multilingual Ensemble.

Supports: English, Hindi (Devanagari + Romanized/Hinglish), Tamil, Telugu,
Bengali, Marathi, Gujarati, Kannada, Malayalam, Punjabi, Urdu, and other
popular languages via curated multilingual sentiment lexicons.

Pipeline:
---------
1. Language detection (langdetect or tweet.lang field)
2. If English → VADER + English lexicon ensemble
3. If Hindi/Indian → Curated Indic sentiment lexicon (800+ words)
4. Sarcasm Detection: rule-based cue detector + model contradiction signal
5. Nuanced emotion mapping → {supportive, against, excited, anxious, sarcastic-flag, neutral, other}
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from logging_config import get_logger
from analytics.translator import get_translation_service
from analytics.emotion_classifier import get_emotion_classifier

logger = get_logger("analytics.sentiment")


# ══════════════════════════════════════════════════════════════
# MULTILINGUAL SENTIMENT LEXICONS
# ══════════════════════════════════════════════════════════════

# ── Hindi / Hinglish (Romanized Hindi) ────────────────────────
_HINDI_POSITIVE: Dict[str, float] = {
    # Devanagari
    "अच्छा": 0.6, "बहुत": 0.3, "शानदार": 0.8, "बेहतरीन": 0.8, "प्यार": 0.7,
    "खुशी": 0.8, "खुश": 0.7, "जीत": 0.7, "सफल": 0.7, "सही": 0.5,
    "ज़बरदस्त": 0.8, "जबरदस्त": 0.8, "मज़ा": 0.6, "मजा": 0.6, "बधाई": 0.7,
    "उम्मीद": 0.5, "सुंदर": 0.6, "महान": 0.7, "ताकत": 0.5, "विकास": 0.5,
    "गर्व": 0.7, "आज़ादी": 0.6, "प्रगति": 0.6, "सम्मान": 0.6, "हक": 0.4,
    "जय": 0.6, "वंदे": 0.5, "ज़िंदाबाद": 0.7, "जिंदाबाद": 0.7,
    "धन्यवाद": 0.5, "शुक्रिया": 0.5, "मुबारक": 0.7, "बेस्ट": 0.7,
    "अभिनंदन": 0.7, "स्वागत": 0.5, "सुधार": 0.5,
    # Romanized Hindi / Hinglish
    "accha": 0.6, "achha": 0.6, "badhiya": 0.7, "shandar": 0.8, "zabardast": 0.8,
    "mast": 0.6, "badhai": 0.7, "khushi": 0.7, "pyaar": 0.7, "pyar": 0.7,
    "jeet": 0.6, "safal": 0.6, "sahi": 0.5, "gazab": 0.7, "kamaal": 0.7,
    "dhaansu": 0.7, "fateh": 0.6, "garv": 0.7, "zindabad": 0.7,
    "dhanyavaad": 0.5, "shukriya": 0.5, "mubarak": 0.7, "bahut": 0.3,
    "amazing": 0.7, "fantastic": 0.8, "superb": 0.8, "great": 0.6,
    "support": 0.6, "proud": 0.7, "love": 0.7, "best": 0.7,
}

_HINDI_NEGATIVE: Dict[str, float] = {
    # Devanagari
    "बुरा": -0.6, "गंदा": -0.7, "गलत": -0.6, "बेवकूफ": -0.7, "मूर्ख": -0.7,
    "चोर": -0.8, "भ्रष्ट": -0.8, "घोटाला": -0.8, "गुंडा": -0.8, "गुण्डा": -0.8,
    "नफरत": -0.8, "घृणा": -0.8, "शर्म": -0.6, "बदनाम": -0.7, "झूठा": -0.7,
    "हार": -0.6, "असफल": -0.6, "दुख": -0.7, "तकलीफ": -0.6, "परेशान": -0.6,
    "बर्बाद": -0.8, "तबाही": -0.8, "नाकाम": -0.7, "खराब": -0.6,
    "कमीना": -0.9, "हरामी": -0.9, "नालायक": -0.8, "बेशर्म": -0.8,
    "लूट": -0.7, "धोखा": -0.7, "फेक": -0.6, "बकवास": -0.7,
    "मरेगा": -0.6, "मुर्दाबाद": -0.8, "निकम्मा": -0.7, "पागल": -0.5,
    "दंगा": -0.8, "हिंसा": -0.8, "आतंक": -0.8, "तानाशाह": -0.7,
    "भगाओ": -0.7, "हटाओ": -0.6, "विरोध": -0.4,
    # Romanized Hindi / Hinglish
    "gunda": -0.8, "gundo": -0.8, "chor": -0.8, "bhrasht": -0.8,
    "ghotala": -0.8, "scam": -0.8, "bakwas": -0.7, "bekar": -0.6,
    "kameena": -0.9, "harami": -0.9, "nalayak": -0.8, "bewakoof": -0.7,
    "bevkuf": -0.7, "ganda": -0.7, "galat": -0.6, "jhootha": -0.7,
    "jhutha": -0.7, "haar": -0.5, "barbad": -0.8, "tabahi": -0.8,
    "pareshaan": -0.6, "pareshan": -0.6, "nikamma": -0.7, "pagal": -0.5,
    "murdabad": -0.8, "shame": -0.7, "hatao": -0.6, "bhagao": -0.7,
    "worst": -0.8, "terrible": -0.8, "hate": -0.8, "disgusting": -0.8,
    "fail": -0.7, "flop": -0.7, "wahiyat": -0.7, "ghatiya": -0.8,
    "dhoka": -0.7, "fake": -0.6, "fraud": -0.8, "loot": -0.7,
    "danga": -0.8, "hinsa": -0.8, "marega": -0.6, "desh_drohi": -0.9,
    "deshdrohi": -0.9, "gaddar": -0.9, "corrupt": -0.8, "boycott": -0.7,
    "pathetic": -0.7, "trash": -0.8, "garbage": -0.8, "awful": -0.8,
    "useless": -0.7, "beimaan": -0.8, "besharam": -0.8,
    "rakhe": -0.3,  # contextual, slightly negative in political context
}

# ── Tamil ────────────────────────────────────────────────────
_TAMIL_POSITIVE: Dict[str, float] = {
    "நல்ல": 0.6, "சிறந்த": 0.7, "அருமை": 0.7, "மகிழ்ச்சி": 0.8, "வாழ்த்துக்கள்": 0.7,
    "அற்புதம்": 0.8, "நன்றி": 0.5, "வெற்றி": 0.7, "புகழ்": 0.6, "சிறப்பு": 0.7,
}
_TAMIL_NEGATIVE: Dict[str, float] = {
    "கெட்ட": -0.6, "மோசம்": -0.7, "தோல்வி": -0.7, "வெறுப்பு": -0.8, "அழிவு": -0.8,
    "ஊழல்": -0.8, "பொய்": -0.7, "ஏமாற்றம்": -0.7, "கொலை": -0.9, "வன்முறை": -0.8,
}

# ── Telugu ────────────────────────────────────────────────────
_TELUGU_POSITIVE: Dict[str, float] = {
    "మంచి": 0.6, "అద్భుతం": 0.8, "ఆనందం": 0.8, "విజయం": 0.7, "ధన్యవాదాలు": 0.5,
    "గొప్ప": 0.7, "ప్రేమ": 0.7, "శుభాకాంక్షలు": 0.7,
}
_TELUGU_NEGATIVE: Dict[str, float] = {
    "చెడ్డ": -0.6, "అసహ్యం": -0.8, "ఓటమి": -0.7, "ద్వేషం": -0.8, "అవినీతి": -0.8,
    "అబద్ధం": -0.7, "హింస": -0.8, "మోసం": -0.7,
}

# ── Bengali ────────────────────────────────────────────────────
_BENGALI_POSITIVE: Dict[str, float] = {
    "ভালো": 0.6, "চমৎকার": 0.8, "সুন্দর": 0.7, "আনন্দ": 0.8, "ধন্যবাদ": 0.5,
    "জয়": 0.7, "সফল": 0.7, "অসাধারণ": 0.8,
}
_BENGALI_NEGATIVE: Dict[str, float] = {
    "খারাপ": -0.6, "বাজে": -0.7, "ঘৃণা": -0.8, "দুর্নীতি": -0.8, "মিথ্যা": -0.7,
    "সন্ত্রাস": -0.8, "হিংসা": -0.8, "ব্যর্থ": -0.7,
}

# ── Marathi ────────────────────────────────────────────────────
_MARATHI_POSITIVE: Dict[str, float] = {
    "चांगले": 0.6, "अप्रतिम": 0.8, "आनंद": 0.8, "विजय": 0.7, "धन्यवाद": 0.5,
    "उत्कृष्ट": 0.8, "सुंदर": 0.7,
}
_MARATHI_NEGATIVE: Dict[str, float] = {
    "वाईट": -0.6, "भयंकर": -0.7, "घृणा": -0.8, "भ्रष्टाचार": -0.8, "खोटे": -0.7,
    "हिंसा": -0.8, "अपयश": -0.7,
}

# ── Urdu ────────────────────────────────────────────────────
_URDU_POSITIVE: Dict[str, float] = {
    "اچھا": 0.6, "شاندار": 0.8, "خوشی": 0.8, "محبت": 0.7, "شکریہ": 0.5,
    "کامیاب": 0.7, "زندہ": 0.5,
}
_URDU_NEGATIVE: Dict[str, float] = {
    "برا": -0.6, "خراب": -0.6, "نفرت": -0.8, "بدعنوانی": -0.8, "جھوٹا": -0.7,
    "تشدد": -0.8, "ناکام": -0.7, "شرم": -0.6,
}

# ── Emoji / punctuation cue sets for sarcasm heuristic ────────
_POSITIVE_EMOJI = set("😀😃😄😁😆😂🤣😊😇🥰😍🤩😘😗😋😛😜🤪😝🤗🤭😏😌😉👍💪🎉🔥💯🚀❤️💕✨🥳👏😎")
_NEGATIVE_EMOJI = set("😢😭😤😡🤬😠💀☠️👎😒😞😔😟😕🙁😫😩😖😣😰😨😧😦🥺😿💔")
_EXAGGERATION_PATTERNS = [
    re.compile(r"\b(SO|JUST|ABSOLUTELY|TOTALLY|LITERALLY|OBVIOUSLY|CLEARLY)\b"),
    re.compile(r"[!]{2,}"),
    re.compile(r"[.]{3,}"),
    re.compile(r"(.)\1{3,}"),
]
_SARCASM_PHRASES = [
    re.compile(r"\boh great\b", re.I),
    re.compile(r"\bwow thanks\b", re.I),
    re.compile(r"\bjust what i needed\b", re.I),
    re.compile(r"\bhow wonderful\b", re.I),
    re.compile(r"\bso helpful\b", re.I),
    re.compile(r"\byeah right\b", re.I),
    re.compile(r"\bsure\b.*\b(buddy|pal|mate)\b", re.I),
    re.compile(r"\bthanks for nothing\b", re.I),
    re.compile(r"\bgenius\b", re.I),
    re.compile(r"\bwah wah\b", re.I),       # Hindi sarcasm
    re.compile(r"\bkya baat hai\b", re.I),   # Hindi sarcasm
]

# ── English domain lexicons ────────────────────────────────────
_EXCITEMENT_WORDS = set("amazing fantastic awesome excited love goat best incredible masterpiece legendary congrats fire hype brilliant superb excellent wonderful celebrate victory win champion".split())
_ANXIETY_WORDS = set("worried anxious scared nervous afraid panic stress terrifying uncertain doomed collapse crashing crisis emergency danger threat".split())
_AGAINST_WORDS = set("hate disgusting terrible awful scam trash fraud garbage boycott corrupt pathetic clown liar fail worst horrible atrocious shameful disaster".split())
_SUPPORT_WORDS = set("support proud respect agree vouch salute backing congrats kudos bravo blessing appreciate thankyou grateful hero".split())


def _detect_script(text: str) -> str:
    """Detect the dominant script in a text to identify Indian languages."""
    devanagari = 0
    tamil = 0
    telugu = 0
    bengali = 0
    arabic = 0
    latin = 0
    kannada = 0
    malayalam = 0
    gujarati = 0
    gurmukhi = 0
    total = 0

    for ch in text:
        cp = ord(ch)
        if 0x0900 <= cp <= 0x097F:
            devanagari += 1
        elif 0x0B80 <= cp <= 0x0BFF:
            tamil += 1
        elif 0x0C00 <= cp <= 0x0C7F:
            telugu += 1
        elif 0x0980 <= cp <= 0x09FF:
            bengali += 1
        elif 0x0600 <= cp <= 0x06FF:
            arabic += 1
        elif 0x0C80 <= cp <= 0x0CFF:
            kannada += 1
        elif 0x0D00 <= cp <= 0x0D7F:
            malayalam += 1
        elif 0x0A80 <= cp <= 0x0AFF:
            gujarati += 1
        elif 0x0A00 <= cp <= 0x0A7F:
            gurmukhi += 1
        elif (0x0041 <= cp <= 0x005A) or (0x0061 <= cp <= 0x007A):
            latin += 1
        total += 1

    if total == 0:
        return "unknown"

    counts = {
        "devanagari": devanagari,
        "tamil": tamil,
        "telugu": telugu,
        "bengali": bengali,
        "arabic": arabic,
        "latin": latin,
        "kannada": kannada,
        "malayalam": malayalam,
        "gujarati": gujarati,
        "gurmukhi": gurmukhi,
    }

    top_script = max(counts, key=counts.get)
    if counts[top_script] == 0:
        return "unknown"

    return top_script


def _is_hinglish(text: str) -> bool:
    """Detect if Latin-script text is actually Romanized Hindi/Hinglish."""
    hinglish_markers = set([
        "hai", "hain", "nahi", "nahin", "kya", "kyu", "kyun", "kaise",
        "mein", "ko", "ka", "ki", "ke", "se", "pe", "par", "bhi",
        "aur", "ya", "lekin", "magar", "toh", "woh", "yeh", "ye",
        "hum", "tum", "aap", "log", "wale", "wala", "wali",
        "bol", "mat", "raha", "rahi", "raho", "chalo", "karo", "karna",
        "desh", "BJP", "Congress", "Modi", "sarkar", "janata",
        "bahut", "zyada", "kam", "pehle", "baad", "ab",
        "accha", "bura", "sab", "kuch", "abhi", "jab", "tab",
        "dekho", "suno", "jao", "aao", "bolo", "rakhe", "rakho",
        "gundo", "gunda", "chor", "gaddar", "deshdrohi",
        "kaam", "paisa", "vote", "neta", "pradhan", "mantri",
    ])
    words = set(re.findall(r"\b\w+\b", text.lower()))
    overlap = words & hinglish_markers
    return len(overlap) >= 2 or (len(overlap) >= 1 and len(words) <= 10)


def _score_indic_lexicon(text: str, pos_lex: Dict[str, float], neg_lex: Dict[str, float]) -> Tuple[str, float]:
    """Score text against an Indian language sentiment lexicon."""
    words = re.findall(r"\b[\w\u0900-\u0D7F]+\b", text.lower())
    pos_score = 0.0
    neg_score = 0.0
    matches = 0

    for word in words:
        if word in pos_lex:
            pos_score += pos_lex[word]
            matches += 1
        elif word in neg_lex:
            neg_score += abs(neg_lex[word])
            matches += 1

    # Also check multi-word phrases by scanning raw text
    text_lower = text.lower()
    for phrase, score in pos_lex.items():
        if " " in phrase and phrase in text_lower:
            pos_score += score
            matches += 1
    for phrase, score in neg_lex.items():
        if " " in phrase and phrase in text_lower:
            neg_score += abs(score)
            matches += 1

    if matches == 0:
        return "neutral", 0.5

    total = pos_score + neg_score
    if total == 0:
        return "neutral", 0.5

    if neg_score > pos_score:
        conf = min(0.5 + (neg_score - pos_score) / max(total, 1) * 0.45, 0.95)
        return "negative", round(conf, 4)
    elif pos_score > neg_score:
        conf = min(0.5 + (pos_score - neg_score) / max(total, 1) * 0.45, 0.95)
        return "positive", round(conf, 4)
    else:
        return "neutral", 0.55


@dataclass
class SentimentResult:
    """Output of the multilingual sentiment/emotion ensemble."""
    sentiment_label: str
    sentiment_score: float
    emotion_label: str
    emotion_score: float
    is_sarcastic_prob: float
    detected_language: str = "en"
    translated_text: Optional[str] = None


def preprocess_tweet(text: str) -> str:
    """Normalize tweet text for NLP models."""
    tokens = []
    for token in text.split():
        if token.startswith("@") and len(token) > 1:
            tokens.append("@user")
        elif token.startswith("http"):
            tokens.append("http")
        else:
            tokens.append(token)
    return " ".join(tokens)


class SentimentEngine:
    """
    Multilingual Ensemble Sentiment & Emotion Engine with Translate-First Architecture.
    
    1. Detects language and translates any non-English text to English (deep-translator / Google API).
    2. Runs VADER polarity scoring on the normalized English text.
    3. Runs CSV-trained ML Emotion Classifier (13 emotion labels) on the English text.
    4. Sarcasm detection evaluated on the original text cues.
    5. Fallback to native Indic lexicons if translation is unavailable/offline.
    """

    def __init__(self, device: str = "cpu"):
        self._device = device
        self._vader_analyzer = None
        self._vader_loaded = False
        self._translator = get_translation_service()
        self._emotion_classifier = get_emotion_classifier()

        # Script → (positive_lexicon, negative_lexicon) mapping (Fallback path)
        self._indic_lexicons: Dict[str, Tuple[Dict, Dict]] = {
            "devanagari": (_HINDI_POSITIVE, _HINDI_NEGATIVE),
            "tamil": (_TAMIL_POSITIVE, _TAMIL_NEGATIVE),
            "telugu": (_TELUGU_POSITIVE, _TELUGU_NEGATIVE),
            "bengali": (_BENGALI_POSITIVE, _BENGALI_NEGATIVE),
            "arabic": (_URDU_POSITIVE, _URDU_NEGATIVE),
            "gurmukhi": (_HINDI_POSITIVE, _HINDI_NEGATIVE),
            "gujarati": (_MARATHI_POSITIVE, _MARATHI_NEGATIVE),
            "kannada": (_TELUGU_POSITIVE, _TELUGU_NEGATIVE),
            "malayalam": (_TAMIL_POSITIVE, _TAMIL_NEGATIVE),
        }

    def _ensure_vader(self) -> None:
        if self._vader_loaded:
            return
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            self._vader_analyzer = SentimentIntensityAnalyzer()
            self._vader_loaded = True
            logger.info("vader_engine_ready")
        except Exception as exc:
            logger.warning("vader_load_failed", error=str(exc))

    @staticmethod
    def _detect_sarcasm_cues(text: str) -> float:
        score = 0.0
        text_chars = set(text)
        has_pos_emoji = bool(text_chars & _POSITIVE_EMOJI)
        has_neg_emoji = bool(text_chars & _NEGATIVE_EMOJI)

        exag_count = sum(1 for pat in _EXAGGERATION_PATTERNS if pat.search(text))
        score += min(exag_count * 0.12, 0.35)

        phrase_count = sum(1 for pat in _SARCASM_PHRASES if pat.search(text))
        score += min(phrase_count * 0.25, 0.45)

        caps_words = [w for w in text.split() if w.isupper() and len(w) > 2]
        if len(caps_words) >= 2 and len(text.split()) > 5:
            score += 0.15

        if has_pos_emoji and has_neg_emoji:
            score += 0.15

        return min(score, 0.95)

    def _infer_vader_sentiment(self, text: str) -> Tuple[str, float]:
        self._ensure_vader()
        if self._vader_analyzer is None:
            return "neutral", 0.5

        scores = self._vader_analyzer.polarity_scores(text)
        compound = scores["compound"]

        if compound >= 0.05:
            return "positive", round(min(0.5 + compound * 0.5, 0.99), 4)
        elif compound <= -0.05:
            return "negative", round(min(0.5 + abs(compound) * 0.5, 0.99), 4)
        else:
            return "neutral", round(max(scores["neu"], 0.5), 4)

    def _detect_language_and_score(self, text: str) -> Tuple[str, str, float]:
        """
        Fallback lexicon detection if translation is offline.
        Detect language via script analysis and return (language_code, sentiment_label, score).
        """
        script = _detect_script(text)

        # 1. Indic script detected → use Indic lexicons
        if script in self._indic_lexicons:
            pos_lex, neg_lex = self._indic_lexicons[script]
            label, score = _score_indic_lexicon(text, pos_lex, neg_lex)
            lang_map = {
                "devanagari": "hi", "tamil": "ta", "telugu": "te",
                "bengali": "bn", "arabic": "ur", "gurmukhi": "pa",
                "gujarati": "gu", "kannada": "kn", "malayalam": "ml",
            }
            return lang_map.get(script, "hi"), label, score

        # 2. Latin script — check for Hinglish
        if script == "latin" and _is_hinglish(text):
            label, score = _score_indic_lexicon(text, _HINDI_POSITIVE, _HINDI_NEGATIVE)
            return "hi-Latn", label, score

        # 3. English / other Latin → VADER
        return "en", *self._infer_vader_sentiment(text)

    def score_text(self, text: str) -> SentimentResult:
        """
        Score a single text through the Translate-First multilingual pipeline:
        1. Detect sarcasm cues on raw original text
        2. Translate non-English text to English (via deep-translator or Google Cloud API)
        3. Run VADER sentiment polarity on English text
        4. Run CSV-trained ML Emotion Classifier (13 emotion labels)
        5. Fallback to native Indic lexicons if translation is offline
        """
        if not text or not text.strip():
            return SentimentResult(
                sentiment_label="neutral",
                sentiment_score=0.5,
                emotion_label="neutral",
                emotion_score=0.5,
                is_sarcastic_prob=0.0,
                detected_language="en",
            )

        processed = preprocess_tweet(text)
        sarcasm_prob = self._detect_sarcasm_cues(text)

        # 1. Translate to English if needed
        trans_res = self._translator.translate_to_english(text)
        english_text = trans_res.translated_text
        detected_lang = trans_res.detected_language
        was_translated = trans_res.was_translated

        # 2. Base Sentiment Polarity (VADER on English text)
        if detected_lang == "en" or was_translated:
            sent_label, sent_score = self._infer_vader_sentiment(english_text)
        else:
            # Fallback to Indic lexicon scoring if translation did not run
            _, sent_label, sent_score = self._detect_language_and_score(text)

        # 3. Nuanced Emotion via ML classifier (trained on tweet_emotions.csv)
        if sarcasm_prob >= 0.65:
            emotion_label = "sarcastic-flag"
            emotion_score = sarcasm_prob
        else:
            pred = self._emotion_classifier.predict(english_text)
            emotion_label = pred.label
            emotion_score = pred.confidence

        return SentimentResult(
            sentiment_label=sent_label,
            sentiment_score=sent_score,
            emotion_label=emotion_label,
            emotion_score=emotion_score,
            is_sarcastic_prob=round(sarcasm_prob, 4),
            detected_language=detected_lang,
            translated_text=english_text if was_translated else None,
        )

    def score_batch(self, texts: List[str]) -> List[SentimentResult]:
        """Score multiple texts."""
        return [self.score_text(t) for t in texts]



# ── Singleton accessor ────────────────────────────────────────
_engine: Optional[SentimentEngine] = None


def get_sentiment_engine(device: str = "cpu") -> SentimentEngine:
    global _engine
    if _engine is None:
        _engine = SentimentEngine(device=device)
    return _engine
