"""
Verification test for the upgraded Translate-First and CSV-trained Emotion Pipeline.
"""

import sys
from pathlib import Path
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from analytics.sentiment import get_sentiment_engine

from analytics.translator import get_translation_service
from analytics.emotion_classifier import get_emotion_classifier

def test_translation():
    ts = get_translation_service()
    res = ts.translate_to_english("यह एक बहुत अच्छा फोन है")
    print(f"[TEST 1: Translation] Original: यह एक बहुत अच्छा फोन है -> Translated: {res.translated_text} (lang={res.detected_language})")
    assert res.was_translated or res.detected_language == "hi"

def test_emotion_classifier():
    ec = get_emotion_classifier()
    pred_happy = ec.predict("I am having an amazing vacation with family!")
    pred_worry = ec.predict("I am terrified of failing my exam tomorrow, so anxious.")
    print(f"[TEST 2: Emotion] Happy text -> {pred_happy.label} ({pred_happy.confidence})")
    print(f"[TEST 2: Emotion] Worry text -> {pred_worry.label} ({pred_worry.confidence})")
    assert pred_happy.label in ["happiness", "enthusiasm", "fun", "love"]
    assert pred_worry.label in ["worry", "sadness", "empty"]

def test_end_to_end_sentiment():
    engine = get_sentiment_engine()
    cases = [
        ("English Praise", "Antigravity is an incredible tool that makes coding effortless!"),
        ("Hindi Positive", "यह बहुत ही शानदार और उपयोगी है।"),
        ("Hindi Negative", "यह सेवा बहुत घटिया और बेकार है, पैसे बर्बाद हो गए।"),
        ("Tamil Positive", "இது ஒரு சிறந்த தயாரிப்பு"),
        ("Spanish Sadness", "Me siento muy triste y solitario hoy en casa."),
    ]
    print("\n[TEST 3: End-to-End Pipeline]")
    for name, text in cases:
        res = engine.score_text(text)
        trans = f" | Translated: '{res.translated_text}'" if res.translated_text else ""
        print(f"  {name:16} | Lang: {res.detected_language:2} | Sentiment: {res.sentiment_label:8} ({res.sentiment_score:.2f}) | Emotion: {res.emotion_label:10} ({res.emotion_score:.2f}){trans}")
        assert res.sentiment_label in ["positive", "negative", "neutral"]
        assert res.emotion_label != ""

if __name__ == "__main__":
    test_translation()
    test_emotion_classifier()
    test_end_to_end_sentiment()
    print("\nALL TESTS PASSED SUCCESSFULLY!")
