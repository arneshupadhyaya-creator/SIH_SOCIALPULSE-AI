"""
Translation service for the Audience Intelligence Framework.

Translates non-English texts into English prior to running English-tuned NLP
models (VADER, RoBERTa, emotion classifiers).

Features:
- Fast language detection (langdetect + script heuristic fallback)
- User-Agent browser-grade Google Translate requester (no API key required)
- Optional Google Cloud Translation v2 API if GOOGLE_TRANSLATE_API_KEY is configured
- Secondary deep-translator fallback
- In-memory LRU cache to avoid duplicate network calls
- ASCII-safe logging for Windows consoles
- Robust graceful fallback if translation fails or runs offline
"""

from __future__ import annotations

import functools
import re
import requests
import structlog
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import Optional

from config import get_settings

logger = structlog.get_logger(__name__)

# Basic Indic Unicode ranges for quick script detection
_INDIC_RANGES = [
    (0x0900, 0x097F),  # Devanagari (Hindi, Marathi, Sanskrit, Nepali)
    (0x0980, 0x09FF),  # Bengali / Assamese
    (0x0A00, 0x0A7F),  # Gurmukhi (Punjabi)
    (0x0A80, 0x0AFF),  # Gujarati
    (0x0B00, 0x0B7F),  # Oriya
    (0x0B80, 0x0BFF),  # Tamil
    (0x0C00, 0x0C7F),  # Telugu
    (0x0C80, 0x0CFF),  # Kannada
    (0x0D00, 0x0D7F),  # Malayalam
]

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _has_indic_characters(text: str) -> bool:
    for ch in text:
        cp = ord(ch)
        for start, end in _INDIC_RANGES:
            if start <= cp <= end:
                return True
    return False


def _safe_log_str(s: str, max_len: int = 60) -> str:
    """Safely encode strings to ASCII representation to avoid cp1252 Windows console crashes."""
    truncated = s[:max_len]
    return truncated.encode("ascii", "backslashreplace").decode("ascii")


@dataclass
class TranslationResult:
    original_text: str
    translated_text: str
    detected_language: str
    was_translated: bool
    error: Optional[str] = None


class TranslationService:
    """Service to detect language and translate non-English text to English."""

    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.google_translate_api_key
        self._session = requests.Session()
        self._session.headers.update(_BROWSER_HEADERS)
        self._cache: dict[str, tuple[str, str]] = {}  # text -> (translated, lang)
        self._max_cache_size = 4096

    def detect_language(self, text: str) -> str:
        """Detect language code (e.g. 'en', 'hi', 'ta', 'es', 'fr')."""
        clean = re.sub(r"https?://\S+|@\w+|#\w+", "", text).strip()
        if not clean:
            return "en"

        # Check for Indic characters first
        if _has_indic_characters(clean):
            try:
                from langdetect import detect
                return detect(clean)
            except Exception:
                return "hi"  # default Indic fallback

        # If clean text is mostly ASCII letters, test if English
        ascii_chars = sum(1 for c in clean if c.isascii() and c.isalpha())
        total_letters = sum(1 for c in clean if c.isalpha())
        if total_letters > 0 and (ascii_chars / total_letters) > 0.85:
            try:
                from langdetect import detect
                lang = detect(clean)
                return lang
            except Exception:
                return "en"

        try:
            from langdetect import detect
            return detect(clean)
        except Exception:
            return "en"

    def _translate_google_web(self, clean_text: str, sl: str = "auto") -> Optional[str]:
        """Direct browser-style Google Translate call."""
        try:
            r = self._session.get(
                "https://translate.google.com/m",
                params={"sl": sl, "tl": "en", "q": clean_text},
                timeout=6,
            )
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                res = soup.find("div", {"class": "result-container"})
                if res:
                    txt = res.text.strip()
                    lower = txt.lower()
                    if txt and not ("error 500" in lower or "server error" in lower or "that's an error" in lower):
                        return txt
        except Exception as exc:
            logger.debug("translator.web_call_failed", error=str(exc))
        return None

    def translate_to_english(self, text: str) -> TranslationResult:
        """Translate text to English if needed. Returns TranslationResult."""
        if not text or not text.strip():
            return TranslationResult(
                original_text=text,
                translated_text=text,
                detected_language="en",
                was_translated=False,
            )

        # Check cache
        if text in self._cache:
            trans, lang = self._cache[text]
            return TranslationResult(
                original_text=text,
                translated_text=trans,
                detected_language=lang,
                was_translated=(lang != "en"),
            )

        detected_lang = self.detect_language(text)

        # If already English, no translation needed
        if detected_lang == "en":
            self._save_cache(text, text, "en")
            return TranslationResult(
                original_text=text,
                translated_text=text,
                detected_language="en",
                was_translated=False,
            )

        # Needs translation: sanitize punctuation
        clean_text = text.replace("\u0964", ".").replace("\u0965", ".").strip()
        translated_text = text
        was_translated = False
        error_msg = None

        # 1. Try Google Cloud API if API key is provided
        if self.api_key:
            try:
                resp = requests.post(
                    "https://translation.googleapis.com/language/translate/v2",
                    params={"key": self.api_key},
                    json={"q": clean_text, "target": "en"},
                    timeout=5,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    translated_text = data["data"]["translations"][0]["translatedText"]
                    was_translated = True
                    logger.debug("translator.api_success", lang=detected_lang)
                else:
                    error_msg = f"Google API error: {resp.status_code}"
                    logger.warning("translator.api_http_error", status=resp.status_code)
            except Exception as exc:
                error_msg = str(exc)
                logger.warning("translator.api_request_failed", error=str(exc))

        # 2. Browser-grade web translation
        if not was_translated:
            # Try with detected language first
            res = self._translate_google_web(clean_text, sl=detected_lang)
            # Try with auto if detected lang didn't match
            if not res:
                res = self._translate_google_web(clean_text, sl="auto")

            if res:
                translated_text = res
                was_translated = True
                error_msg = None
                logger.info(
                    "translator.translated",
                    src=detected_lang,
                    sample=_safe_log_str(translated_text, 60),
                )

        # 3. Secondary fallback via deep-translator
        if not was_translated:
            try:
                from deep_translator import GoogleTranslator
                candidate = GoogleTranslator(source="auto", target="en").translate(clean_text)
                if candidate and candidate.strip():
                    lower = candidate.lower()
                    if not ("error 500" in lower or "server error" in lower or "that's an error" in lower):
                        translated_text = candidate
                        was_translated = True
                        error_msg = None
            except Exception as exc:
                error_msg = str(exc)
                logger.debug("translator.deep_translator_fallback_failed", error=str(exc))

        if not was_translated:
            logger.warning(
                "translator.translation_failed_will_use_fallback",
                src=detected_lang,
                sample=_safe_log_str(clean_text, 40),
            )

        self._save_cache(text, translated_text, detected_lang)

        return TranslationResult(
            original_text=text,
            translated_text=translated_text,
            detected_language=detected_lang,
            was_translated=was_translated,
            error=error_msg,
        )

    def _save_cache(self, raw: str, trans: str, lang: str):
        if len(self._cache) >= self._max_cache_size:
            # Purge oldest quarter of entries
            keys_to_remove = list(self._cache.keys())[: self._max_cache_size // 4]
            for k in keys_to_remove:
                self._cache.pop(k, None)
        self._cache[raw] = (trans, lang)


@functools.lru_cache(maxsize=1)
def get_translation_service() -> TranslationService:
    """Singleton getter for TranslationService."""
    return TranslationService()
