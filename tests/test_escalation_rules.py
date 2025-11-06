"""Tests for escalation rules - Safety-critical checks only.

After refactoring, escalation_rules.py only handles:
1. Links/screenshots (legal/compliance requirement)
2. Cold follow-up detection (3+ consecutive AI messages)
3. Simple acknowledgment filtering

All other escalations (fees, pricing, scheduling, approved, etc.) are now
handled by the LLM through comprehensive prompts.
"""

from app.services.escalation_rules import (
    detect_escalation_from_rules,
    assistant_streak,
)


def _mk_history(assistant_count: int) -> list[dict[str, str]]:
    """Helper to create chat history with N consecutive assistant messages."""
    history: list[dict[str, str]] = []
    for _ in range(assistant_count):
        history.append({"role": "assistant", "content": "Ping"})
    return history


# ============================================================================
# SAFETY-CRITICAL RULES (Still handled by escalation_rules.py)
# ============================================================================

def test_links_escalates_links():
    """Links in message should always escalate (legal/compliance)."""
    res = detect_escalation_from_rules(
        user_text="Check this https://example.com",
        chat_history=[],
        stage="working",
        reply_text=None,
    )
    assert res and res.get("action") == "escalate_links"


def test_screenshot_escalates_links():
    """Screenshot references should always escalate (legal/compliance)."""
    res = detect_escalation_from_rules(
        user_text="see screenshot",
        chat_history=[],
        stage="working",
        reply_text=None,
    )
    assert res and res.get("action") == "escalate_links"


def test_social_media_escalates_links():
    """Social media links should always escalate."""
    for social in ["instagram", "facebook", "tiktok"]:
        res = detect_escalation_from_rules(
            user_text=f"check my {social}",
            chat_history=[],
            stage="working",
            reply_text=None,
        )
        assert res and res.get("action") == "escalate_links", f"{social} should escalate"


def test_cold_followup_assistant_streak():
    """3+ consecutive assistant messages without user response should escalate."""
    res = detect_escalation_from_rules(
        user_text="",
        chat_history=_mk_history(3),
        stage="working",
        reply_text=None,
    )
    assert res and res.get("action") == "escalate_followup"


def test_cold_followup_not_triggered_with_text():
    """Cold follow-up should NOT trigger if user sent substantive text."""
    res = detect_escalation_from_rules(
        user_text="I'm interested in The Pearl",
        chat_history=_mk_history(3),
        stage="working",
        reply_text=None,
    )
    # Should not escalate for cold follow-up (text present)
    # Links/screenshots rule may still apply if text contains them
    assert res is None or res.get("action") != "escalate_followup"


def test_acknowledgment_no_escalation():
    """Simple acknowledgments should not trigger escalation."""
    acknowledgments = ["Thanks", "thank you", "Okay", "ok", "Sure", "Got it", "Cool"]
    for ack in acknowledgments:
        res = detect_escalation_from_rules(
            user_text=ack,
            chat_history=[],
            stage="working",
            reply_text=None,
        )
        assert res is None, f"'{ack}' should not escalate"


def test_assistant_streak_counts():
    """Helper function should correctly count consecutive assistant messages."""
    hist = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
        {"role": "assistant", "content": "Follow up 1"},
        {"role": "assistant", "content": "Follow up 2"},
    ]
    assert assistant_streak(hist) == 3


def test_assistant_streak_resets_on_user():
    """Assistant streak should reset when user responds."""
    hist = [
        {"role": "assistant", "content": "Ping 1"},
        {"role": "assistant", "content": "Ping 2"},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Ping 3"},
    ]
    assert assistant_streak(hist) == 1


# ============================================================================
# LLM-HANDLED CASES (Should NOT be caught by rules - LLM handles these)
# ============================================================================

def test_fees_not_detected_by_rules():
    """Fee questions should be handled by LLM, not rules."""
    res = detect_escalation_from_rules(
        user_text="What are the application and admin fees?",
        chat_history=[],
        stage="qualifying",
        reply_text=None,
    )
    # Rules should NOT escalate - LLM handles this
    assert res is None


def test_scheduling_not_detected_by_rules():
    """Scheduling requests should be handled by LLM, not rules."""
    res = detect_escalation_from_rules(
        user_text="Can we schedule a tour Friday?",
        chat_history=[],
        stage="touring",
        reply_text=None,
    )
    # Rules should NOT escalate - LLM handles this
    assert res is None


def test_more_options_not_detected_by_rules():
    """More options requests should be handled by LLM, not rules."""
    res = detect_escalation_from_rules(
        user_text="Can you send more options?",
        chat_history=[],
        stage="working",
        reply_text=None,
    )
    # Rules should NOT escalate - LLM handles this
    assert res is None


def test_approved_not_detected_by_rules():
    """Approval notifications should be handled by LLM, not rules."""
    res = detect_escalation_from_rules(
        user_text="My application was approved!",
        chat_history=[],
        stage="applied",
        reply_text=None,
    )
    # Rules should NOT escalate - LLM handles this
    assert res is None


def test_pricing_not_detected_by_rules():
    """Specific pricing questions should be handled by LLM, not rules."""
    res = detect_escalation_from_rules(
        user_text="What's the price for Harlow right now? Any specials?",
        chat_history=[],
        stage="working",
        reply_text=None,
    )
    # Rules should NOT escalate - LLM handles this
    assert res is None


def test_complaint_not_detected_by_rules():
    """Complaints should be handled by LLM, not rules."""
    res = detect_escalation_from_rules(
        user_text="Maintenance is not working in my unit",
        chat_history=[],
        stage="approved",
        reply_text=None,
    )
    # Rules should NOT escalate - LLM handles this
    assert res is None


# ============================================================================
# EDGE CASES
# ============================================================================

def test_empty_text_and_history():
    """Empty text with no history should not escalate."""
    res = detect_escalation_from_rules(
        user_text="",
        chat_history=[],
        stage="working",
        reply_text=None,
    )
    assert res is None


def test_whitespace_only_text():
    """Whitespace-only text should be treated as empty."""
    res = detect_escalation_from_rules(
        user_text="   \n\t  ",
        chat_history=[],
        stage="working",
        reply_text=None,
    )
    assert res is None


def test_multiple_safety_violations():
    """Multiple safety violations should return the first detected."""
    # Links + fees (links is checked first)
    res = detect_escalation_from_rules(
        user_text="Check https://example.com and what are the fees?",
        chat_history=[],
        stage="working",
        reply_text=None,
    )
    assert res and res.get("action") == "escalate_links"


def test_link_with_acknowledgment():
    """Links should escalate even if message looks like acknowledgment."""
    res = detect_escalation_from_rules(
        user_text="Thanks! https://example.com",
        chat_history=[],
        stage="working",
        reply_text=None,
    )
    # Link detection should override acknowledgment filtering
    # (acknowledgment check happens first, but links are safety-critical)
    # Actually, looking at the code, acknowledgment returns None early
    # So this tests that acknowledgment + link doesn't prevent escalation
    assert res and res.get("action") == "escalate_links"
