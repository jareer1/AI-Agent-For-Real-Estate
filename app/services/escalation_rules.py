"""Simplified escalation rules for critical safety checks.

This module provides minimal rule-based escalation detection for cases where
LLM-driven detection needs a safety backup. Most escalation logic is now
handled through comprehensive prompts in the LLM.

The rules here are strictly for:
1. Hard safety requirements (links, screenshots)
2. Backup detection when LLM doesn't provide action
3. Critical business rules that must never be missed
"""

from __future__ import annotations
from typing import Any, Dict, Optional


def _contains_link_or_screenshot(text: str) -> bool:
    """Detect if text contains links or screenshot references.
    
    This is a safety-critical check - we never want to respond to links
    or screenshots without human review.
    """
    t = (text or "").lower()
    
    # URL patterns
    if any(k in t for k in ["http://", "https://", "www."]):
        return True
    
    # Social media references
    if any(k in t for k in ["instagram", "facebook", "tiktok", "twitter", "x.com", "youtube", "youtu.be"]):
        return True
    
    # Screenshot/image references
    if any(k in t for k in ["screenshot", "screen shot", "see pic", "see image", "check pic", "attached"]):
        return True
    
    return False


def _assistant_streak(chat_history: list[dict[str, str]] | None) -> int:
    """Count consecutive assistant messages without user response.
    
    Used to detect cold leads that need follow-up escalation.
    """
    if not chat_history:
        return 0
    
    count = 0
    for msg in reversed(chat_history):
        if (msg.get("role") or "").lower() == "assistant" and (msg.get("content") or "").strip():
            count += 1
        else:
            break
    
    return count


def _is_simple_acknowledgment(text: str) -> bool:
    """Detect if message is just a simple acknowledgment.
    
    Simple acknowledgments shouldn't trigger escalations by themselves.
    
    Note: Empty text is NOT considered an acknowledgment - empty text
    might indicate cold lead (no response), which should be handled separately.
    """
    t = (text or "").strip().lower()
    
    # Empty text is NOT an acknowledgment (could be cold lead)
    if not t:
        return False
    
    # Very short text (1 char) could be acknowledgment
    if len(t) < 2:
        return t in ["k"]  # Only "k" is a valid single-char acknowledgment
    
    # Single-word acknowledgments
    simple_acks = ["ok", "k", "okay", "thanks", "thx", "cool", "sure", "yes", "no", "yep", "nope"]
    if t in simple_acks or t in [f"{w}!" for w in simple_acks]:
        return True
    
    # Short phrase acknowledgments
    short_phrases = ["got it", "sounds good", "thank you", "no worries", "all good"]
    if any(t.startswith(phrase) and len(t) <= len(phrase) + 5 for phrase in short_phrases):
        return True
    
    return False


def detect_escalation_from_rules(
    user_text: str,
    chat_history: list[dict[str, str]] | None,
    stage: Any,
    reply_text: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """Apply minimal rule-based escalation detection as safety backup.
    
    This function should only catch critical cases that must never be missed.
    Most escalation logic is now handled by the LLM through prompts.
    
    Returns:
        Dict with {"action": "action_name", "reason": "explanation"} or None
    
    Safety Rules:
    1. Links/screenshots → MUST escalate (legal/compliance)
    2. Cold follow-up (3+ assistant messages) → escalate for human attention
    3. Simple acknowledgments → do NOT escalate
    
    All other escalations (fees, pricing, scheduling, etc.) are handled by LLM.
    """
    text = (user_text or "").strip()
    
    # Safety Rule 1: Simple acknowledgments should not escalate
    if _is_simple_acknowledgment(text):
        return None
    
    # Safety Rule 2: Links and screenshots (CRITICAL - legal/compliance requirement)
    if _contains_link_or_screenshot(text):
        return {"action": "escalate_links", "reason": "contains_link_or_screenshot"}
    
    # Safety Rule 3: Cold follow-up detection (3+ consecutive assistant messages)
    # Only when there's no substantive incoming text
    if not text and _assistant_streak(chat_history) >= 3:
        return {"action": "escalate_followup", "reason": "cold_lead_followup"}
    
    # All other escalations (fees, pricing, scheduling, approved, etc.) are handled by LLM
    return None


def assistant_streak(chat_history: list[dict[str, str]] | None) -> int:
    """Public API for assistant streak counting.
    
    Exported for backward compatibility with existing code.
    """
    return _assistant_streak(chat_history)
