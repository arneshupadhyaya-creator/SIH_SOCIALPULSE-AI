"""
Application configuration via pydantic-settings.

All config is loaded from environment variables / .env file.
Scraper credentials are in a separate accounts.txt — never in .env.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration loaded from .env (never hardcode secrets)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Database ──────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/audience_intel"
    sync_database_url: str = "postgresql+psycopg2://postgres:postgres@db:5432/audience_intel"

    # ── Scraper ───────────────────────────────────────────────
    accounts_file: str = "accounts.txt"
    scrape_delay_min: float = 2.0
    scrape_delay_max: float = 5.0
    circuit_breaker_threshold: int = 5   # errors in window before tripping
    circuit_breaker_timeout: int = 300   # seconds to pause after tripping

    # ── NLP / Models ──────────────────────────────────────────
    device: str = "cpu"                  # "cpu" or "cuda"
    hf_cache_dir: str = "models_cache"
    sentiment_model: str = "cardiffnlp/twitter-roberta-base-sentiment-latest"
    emotion_model: str = "j-hartmann/emotion-english-distilroberta-base"
    zeroshot_model: str = "facebook/bart-large-mnli"
    spacy_model: str = "en_core_web_sm"
    google_translate_api_key: str = ""   # optional; deep-translator free tier used if empty
    emotion_csv_path: str = "emotions/tweet_emotions.csv"


    # ── Trends ────────────────────────────────────────────────
    trend_window_minutes: int = 15
    trend_top_n: int = 20

    # ── Logging ───────────────────────────────────────────────
    log_level: str = "INFO"

    # ── API ───────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # ── Helpers ───────────────────────────────────────────────
    @property
    def accounts_path(self) -> Path:
        return Path(self.accounts_file)


@lru_cache
def get_settings() -> Settings:
    """Singleton accessor — import this instead of constructing Settings()."""
    return Settings()
