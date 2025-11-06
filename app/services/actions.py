"""Action handling and routing for agent responses.

This module defines action types, stage transitions, and message sending rules.
Simplified to remove hardcoded response templates - the LLM handles response
generation through comprehensive prompts.
"""

from typing import Any, Optional
import logging


class ActionExtractor:
    """Action detection interface (deprecated - now LLM-driven).
    
    Kept for backward compatibility. All action detection is now handled
    by the LLM through structured JSON output.
    """
    
    def detect(self, text: str) -> dict[str, Any] | None:
        """Deprecated: LLM handles all action detection.
        
        Returns None to indicate no keyword-based detection.
        """
        logging.getLogger(__name__).debug("ActionExtractor.detect is deprecated (LLM-driven)")
        return None


# Action Type Definitions
ESCALATION_ACTIONS = [
    "escalate_fees",        # Fee questions (no-send)
    "escalate_links",       # Links/screenshots (no-send)
    "escalate_pricing",     # Specific property pricing (no-send)
    "escalate_complaint",   # Post-move complaints (no-send in post-close stages)
    "escalate_scheduling",  # Tour scheduling (send)
    "escalate_more_options",# Sending property options (send)
    "escalate_approved",    # Lead approved (send)
    "escalate_followup",    # Cold lead follow-up (send)
    "escalate_uncertainty", # Lead uncertainty/hesitation (send)
    "escalate_general",     # General escalation (send)
]

NON_ESCALATION_ACTIONS = [
    "request_application",  # Lead ready to apply
]


def should_change_stage(suggested_action: dict[str, Any] | None) -> str | None:
    """Determine if the suggested action should trigger a stage change.
    
    Most actions don't change stage - they just flag for human review.
    Only application-related actions trigger stage transitions.
    
    Args:
        suggested_action: Action dict with "action" key
    
    Returns:
        New stage name or None if no change
    """
    if not suggested_action:
        return None
    
    action = suggested_action.get("action")
    
    # Application triggers stage change to "applied"
    if action == "request_application":
        return "applied"
    
    # All escalations stay in current stage
    if action in ESCALATION_ACTIONS:
        return None
    
    return None


def is_escalation_action(action: str | None) -> bool:
    """Check if an action is an escalation type.
    
    Args:
        action: Action name string
    
    Returns:
        True if action requires escalation/human review
    """
    if not action:
        return False
    
    return action in ESCALATION_ACTIONS


def determine_should_send(
    action: Optional[str],
    stage: Optional[str],
    reason: Optional[str] = None
) -> bool:
    """Determine whether the AI should send a message based on action type.
    
    Critical business rules for when to suppress messages:
    - Links/screenshots: Never send (legal/compliance)
    - Fees: Never send (must be accurate, human-verified)
    - Specific pricing: Never send (must be accurate, human-verified)
    - Post-move complaints: Never send (requires human empathy/resolution)
    
    Args:
        action: Action name (escalate_*, request_*, etc.)
        stage: Current conversation stage
        reason: Optional reason for action
    
    Returns:
        True if message should be sent, False to suppress
    """
    a = (action or "").lower().strip()
    s = (stage or "").strip().lower()
    
    # Critical no-send actions (safety/compliance)
    NO_SEND_ACTIONS = ["escalate_links", "escalate_fees", "escalate_pricing"]
    if a in NO_SEND_ACTIONS:
        return False
    
    # Post-move complaints require human handling (no AI response)
    if a == "escalate_complaint":
        post_move_stages = ["approved", "closed", "post_close_nurture", "post close nurture", "postclose"]
        if s in post_move_stages:
            return False
        return True
    
    # All other actions: send message
    # (escalate_scheduling, escalate_more_options, escalate_approved, etc.)
    return True


def default_reply_for_action(
    action: Optional[str],
    stage: Optional[str],
    user_text: str = ""
) -> str:
    """DEPRECATED: Provide fallback reply when LLM doesn't generate one.
    
    This should rarely be used - the LLM should always provide outgoing_message.
    Only used as last-resort safety when LLM fails completely.
    
    Args:
        action: Action name
        stage: Current stage
        user_text: User's message (unused in simplified version)
    
    Returns:
        Minimal safe response or empty string
    """
    a = (action or "").lower().strip()
    s = (stage or "").strip().lower()
    
    # No-send actions: return empty
    if a in ["escalate_links", "escalate_fees", "escalate_pricing"]:
        return ""
    
    # Post-move complaints: return empty
    if a == "escalate_complaint":
        post_move_stages = ["approved", "closed", "post_close_nurture", "post close nurture", "postclose"]
        if s in post_move_stages:
            return ""
    
    # For send actions, provide minimal safe fallback
    # (LLM should normally handle this)
    minimal_responses = {
        "escalate_scheduling": "I'll check availability and follow up with times.",
        "escalate_more_options": "I'll take another look and send a few fresh options.",
        "escalate_approved": "Congratulations! I'll follow up on next steps.",
        "escalate_followup": "Just checking in—let me know if you want to move forward.",
        "escalate_uncertainty": "Totally understandable. I'll take another pass and send a few fresh options.",
        "escalate_general": "I'll look into that and follow up shortly.",
    }
    
    return minimal_responses.get(a, "I'll look into that and follow up shortly.")
