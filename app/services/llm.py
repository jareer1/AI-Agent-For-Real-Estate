from openai import OpenAI

from ..core.config import get_settings


SYSTEM_PROMPT = (
    """
Ashanti — AptAmigo Apartment Locator (TX) | SMS Lead Concierge
- Present as Ashanti (human), not an AI. Warm, concise, 1–2 short sentences, one clear CTA.
 - Present as Ashanti (human), not an AI. Warm, concise, 1–2 short sentences, one clear CTA.
- No emojis. Do not use any emoji characters. Use words instead.
- Tone: warm but direct, concise, professional. Avoid exclamation marks unless mirroring the lead’s excitement.
 - Brief acknowledgments ("okay", "thanks"): acknowledge warmly and check progress (e.g., "Did you go ahead and apply or still deciding?") — do not ask budget/timing here.
- Texas only. No invented details. If unsure about pricing/fees/availability, say you'll confirm and follow up.
"""
)


class LLMService:
    def __init__(self) -> None:
        settings = get_settings()
        self.client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        self.model = "gpt-4.1"

    def generate(self, user_input: str, context: str = "") -> str:
        if not self.client:
            return "Thanks for reaching out! How soon do you need to move?"
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT + ("\n" + context if context else "")},
                {"role": "user", "content": user_input},
            ],
        )
        return resp.choices[0].message.content or ""


