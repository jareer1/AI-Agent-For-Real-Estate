from __future__ import annotations

from app.services.followup_detector import FollowUpPromiseDetector


def test_followup_detector_positive_strong_phrases():
    d = FollowUpPromiseDetector()
    samples = [
        "I'll get back to you shortly.",
        "I will follow up tomorrow.",
        "I'll confirm and get back to you.",
        "We'll check and get back.",
        "Let me confirm and I'll update you.",
        "I'll check in tomorrow with some more options.",
    ]
    for s in samples:
        res = d.detect(s)
        assert res["is_followup"] is True
        assert res["confidence"] >= 0.6


def test_followup_detector_negative_controls():
    d = FollowUpPromiseDetector()
    negatives = [
        "You're welcome!",
        "Let me know if you have questions.",
        "We discussed this already.",
        "This is a summary of your options.",
    ]
    for s in negatives:
        res = d.detect(s)
        assert res["is_followup"] is False or res["confidence"] < 0.6



