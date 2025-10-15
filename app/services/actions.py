from typing import Any


class ActionExtractor:
    def detect(self, text: str) -> dict[str, Any] | None:
        lower = text.lower()
        if "schedule" in lower or "tour" in lower:
            return {"action": "schedule_tour"}
        if "apply" in lower or "application" in lower:
            return {"action": "request_application"}
        return None


def should_change_stage(suggested_action: dict[str, Any] | None) -> str | None:
    if not suggested_action:
        return None
    act = suggested_action.get("action")
    if act == "schedule_tour":
        return "touring"
    if act == "request_application":
        return "applied"
    return None


