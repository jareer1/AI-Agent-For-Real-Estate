from typing import Any


class ActionExtractor:
    def detect(self, text: str) -> dict[str, Any] | None:
        lower = text.lower()
        if "apply" in lower or "application" in lower:
            return {"action": "request_application"}
        # Pricing/availability queries should escalate to human for accuracy
        pricing_keywords = [
            "price", "pricing", "rate", "rent", "special", "promo", "deal",
            "available now", "availability", "unit available", "floorplan", "quote",
        ]
        if any(k in lower for k in pricing_keywords):
            return {"action": "escalate_pricing"}
        return None


def should_change_stage(suggested_action: dict[str, Any] | None) -> str | None:
    if not suggested_action:
        return None
    act = suggested_action.get("action")
    if act == "request_application":
        return "applied"
    if act == "escalate_pricing":
        # Stay in working/touring; no automatic stage change
        return None
    return None


