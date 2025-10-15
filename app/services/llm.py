from openai import OpenAI

from ..core.config import get_settings


SYSTEM_PROMPT = (
    "You are a professional apartment leasing agent. Be concise, friendly, and proactive."
)


class LLMService:
    def __init__(self) -> None:
        settings = get_settings()
        self.client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        self.model = "gpt-4o-mini"

    def generate(self, user_input: str, context: str = "") -> str:
        if not self.client:
            return "Thanks for reaching out! How soon do you need to move?"
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT + ("\n" + context if context else "")},
                {"role": "user", "content": user_input},
            ],
            temperature=0.4,
        )
        return resp.choices[0].message.content or ""


