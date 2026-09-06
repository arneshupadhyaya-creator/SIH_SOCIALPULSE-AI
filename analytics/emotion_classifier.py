"""
Machine-Learned Emotion Classifier trained on `emotions/tweet_emotions.csv`.

Provides 13 nuanced emotion labels:
- anger
- boredom
- empty
- enthusiasm
- fun
- happiness
- hate
- love
- neutral
- relief
- sadness
- surprise
- worry

Pipeline:
TF-IDF (1-2 ngrams, 30k features) + Logistic Regression.
Model is automatically trained on first start and cached to `emotions/emotion_model.joblib`.
If the model file exists, it loads in milliseconds.
"""

from __future__ import annotations

import csv
import functools
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Tuple

import structlog
from config import get_settings

logger = structlog.get_logger(__name__)

# Fallback emotion keyword dictionary if model is not yet loaded or fails
_FALLBACK_EMOTION_KEYWORDS: dict[str, list[str]] = {
    "happiness": ["happy", "joy", "blessed", "wonderful", "delighted", "glad", "celebrate", "great", "awesome"],
    "enthusiasm": ["excited", "pumped", "can't wait", "hyped", "thrilled", "eager", "looking forward", "let's go"],
    "love": ["love", "adore", "cherish", "sweetheart", "in love", "my favorite", "heart", "beautiful"],
    "fun": ["haha", "lol", "lmao", "funny", "hilarious", "joke", "party", "laugh", "having fun"],
    "relief": ["relief", "relieved", "thank goodness", "finally", "whew", "phew", "glad that's over"],
    "surprise": ["wow", "omg", "shocked", "surprised", "unexpected", "unbelievable", "whoa", "holy"],
    "sadness": ["sad", "depressed", "unhappy", "cry", "crying", "heartbroken", "gloomy", "mourning", "miss you", "grief"],
    "worry": ["worried", "anxious", "nervous", "scared", "fear", "stress", "panic", "trouble", "concerned", "headache"],
    "anger": ["angry", "mad", "pissed", "furious", "outrage", "disgusted", "annoyed", "irritated", "stupid"],
    "hate": ["hate", "despise", "loathe", "terrible", "worst", "garbage", "trash", "disgusting"],
    "boredom": ["bored", "boring", "dull", "nothing to do", "monotonous", "sleepy"],
    "empty": ["empty", "numb", "hollow", "lost", "exhausted", "drained"],
    "neutral": ["ok", "okay", "fine", "average", "normal", "standard"],
}


@dataclass
class EmotionPrediction:
    label: str
    confidence: float
    probabilities: Dict[str, float]


def _clean_text_for_emotion(text: str) -> str:
    """Normalize text: strip urls, mentions, clean whitespace."""
    t = re.sub(r"https?://\S+", "", text)
    t = re.sub(r"@\w+", "", t)
    t = re.sub(r"#", "", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


class EmotionClassifier:
    """Trained classifier for 13 emotion categories."""

    def __init__(self, model_path: Optional[str] = None, csv_path: Optional[str] = None):
        settings = get_settings()
        self.csv_path = Path(csv_path or settings.emotion_csv_path)
        self.model_path = Path(model_path or "emotions/emotion_model.joblib")
        self._pipeline = None
        self._classes: list[str] = []
        self._load_or_train()

    def _load_or_train(self):
        """Load cached model from disk or train fresh from CSV."""
        import joblib

        if self.model_path.exists():
            try:
                logger.info("emotion_classifier.loading_cached_model", path=str(self.model_path))
                self._pipeline = joblib.load(self.model_path)
                self._classes = list(self._pipeline.classes_)
                logger.info("emotion_classifier.loaded", classes_count=len(self._classes))
                return
            except Exception as exc:
                logger.warning("emotion_classifier.load_failed_will_retrain", error=str(exc))

        # Train from CSV
        if not self.csv_path.exists():
            logger.warning("emotion_classifier.csv_not_found", path=str(self.csv_path))
            return

        try:
            self._train()
        except Exception as exc:
            logger.error("emotion_classifier.training_failed", error=str(exc))

    def _train(self):
        """Train TF-IDF + Logistic Regression on tweet_emotions.csv."""
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        import joblib
        import time

        logger.info("emotion_classifier.training_started", csv=str(self.csv_path))
        t0 = time.time()

        texts: list[str] = []
        labels: list[str] = []

        with open(self.csv_path, mode="r", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f)
            # Skip header: tweet_id,sentiment,content
            header = next(reader, None)
            for row in reader:
                if len(row) >= 3:
                    lbl = row[1].strip().lower()
                    raw = row[2].strip()
                    cleaned = _clean_text_for_emotion(raw)
                    if lbl and cleaned:
                        labels.append(lbl)
                        texts.append(cleaned)

        if not texts:
            logger.warning("emotion_classifier.no_data_in_csv")
            return

        logger.info("emotion_classifier.dataset_loaded", samples=len(texts), duration=f"{time.time() - t0:.2f}s")

        pipe = Pipeline([
            ("tfidf", TfidfVectorizer(
                ngram_range=(1, 2),
                max_features=30000,
                sublinear_tf=True,
                stop_words="english",
            )),
            ("clf", LogisticRegression(
                C=1.0,
                max_iter=250,
                solver="lbfgs",
                random_state=42,
            )),
        ])

        t1 = time.time()
        pipe.fit(texts, labels)
        self._pipeline = pipe
        self._classes = list(pipe.classes_)
        train_time = time.time() - t1
        logger.info("emotion_classifier.trained", duration=f"{train_time:.2f}s", classes=self._classes)

        # Save model
        try:
            self.model_path.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(pipe, self.model_path, compress=3)
            logger.info("emotion_classifier.saved", path=str(self.model_path))
        except Exception as exc:
            logger.warning("emotion_classifier.save_failed", error=str(exc))

    def predict(self, text: str) -> EmotionPrediction:
        """Predict fine-grained emotion for given English text."""
        cleaned = _clean_text_for_emotion(text)
        if not cleaned:
            return EmotionPrediction(label="neutral", confidence=0.5, probabilities={"neutral": 1.0})

        # If pipeline is loaded and ready
        if self._pipeline is not None:
            try:
                probs = self._pipeline.predict_proba([cleaned])[0]
                best_idx = probs.argmax()
                best_label = str(self._classes[best_idx])
                confidence = float(probs[best_idx])
                prob_dict = {str(cls): float(probs[i]) for i, cls in enumerate(self._classes)}
                return EmotionPrediction(
                    label=best_label,
                    confidence=round(confidence, 4),
                    probabilities=prob_dict,
                )
            except Exception as exc:
                logger.warning("emotion_classifier.predict_failed", error=str(exc))


        # Fallback to keyword matcher if ML model is unavailable
        return self._predict_fallback(cleaned)

    def _predict_fallback(self, text: str) -> EmotionPrediction:
        lower = text.lower()
        counts: dict[str, int] = {}
        for emotion, keywords in _FALLBACK_EMOTION_KEYWORDS.items():
            for kw in keywords:
                if re.search(r"\b" + re.escape(kw) + r"\b", lower):
                    counts[emotion] = counts.get(emotion, 0) + 1

        if not counts:
            return EmotionPrediction(label="neutral", confidence=0.5, probabilities={"neutral": 1.0})

        best_label = max(counts, key=counts.get)
        total = sum(counts.values())
        conf = min(0.95, round(counts[best_label] / total * 0.8 + 0.2, 4))
        return EmotionPrediction(
            label=best_label,
            confidence=conf,
            probabilities={k: round(v / total, 4) for k, v in counts.items()},
        )


@functools.lru_cache(maxsize=1)
def get_emotion_classifier() -> EmotionClassifier:
    """Singleton getter for EmotionClassifier."""
    return EmotionClassifier()
