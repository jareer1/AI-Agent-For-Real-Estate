from typing import Any

from app.core.config import get_settings


class ComposioClient:
    def __init__(self, api_key: str | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.composio_api_key

    def list_tools(self) -> list[str]:
        # Placeholder: return mock tool names
        return ["email.send", "sms.send", "calendar.create_event"]

    def execute(self, tool_name: str, payload: dict[str, Any]) -> dict:
        # Placeholder: emulate tool execution
        return {"tool": tool_name, "payload": payload, "status": "ok", "provider": "composio"}


