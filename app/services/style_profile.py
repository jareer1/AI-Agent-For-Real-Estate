from __future__ import annotations

"""Style profile builder for Ashanti tone guidance.

This service retrieves recent Ashanti agent messages (via existing RAG/MongoDB
retrieval) and synthesizes a compact, tone-only guidance string for the LLM.

Important:
- We DO NOT paste exemplar message content into the prompt.
- We extract phrasing characteristics only (sentence length, acknowledgment use,
  closings, and call-to-action patterns) to avoid content leakage.
"""

from typing import List
import re


def _analyze_messages(messages: List[str]) -> list[str]:
    """Derive tone notes from sample agent messages (not content).

    Produces bullet-style notes that describe style without copying content.
    """
    if not messages:
        return []

    notes: list[str] = []
    total_len = sum(len(m) for m in messages)
    avg_len = total_len / max(len(messages), 1)

    # Sentence length & brevity
    if avg_len < 180:
        notes.append("Keep it brief (1–2 short sentences).")
    else:
        notes.append("Prefer concise phrasing; avoid long paragraphs.")

    # Acknowledgment patterns
    joined = "\n".join(messages)
    lower = joined.lower()
    ack_count = len(re.findall(r"\b(sounds good|got it|you're welcome)\b", lower))
    if ack_count > 0:
        notes.append("Avoid starting messages with acknowledgments; lead with the next step.")

    # Exclamation usage
    exclamations = joined.count("!")
    if exclamations == 0:
        notes.append("Avoid exclamation marks unless mirroring the lead's excitement.")
    else:
        notes.append("Use exclamation marks sparingly.")

    # CTA presence
    cta_signals = [
        "when would you",
        "let me",
        "i'll",
        "i will",
        "can you",
        "would you like",
        "i’ll",
    ]
    if any(sig in lower for sig in cta_signals):
        notes.append("End with one clear next step (CTA), not multiple.")
    else:
        notes.append("Include one concrete next step (CTA).")

    # Filler avoidance
    notes.append("Avoid robotic fillers (e.g., 'let me know if you need anything').")

    return notes


class StyleProfile:
    """Facade to build an Ashanti style profile string."""

    def __init__(self, rag_service) -> None:
        self.rag = rag_service

    def build_style_profile(self, query: str, stage: str | None = None) -> str:
        """Return tone-only guidance derived from agent exemplars.

        We retrieve a few agent messages related to the current query and stage,
        then return a compact set of bullet points describing the style.
        """
        try:
            docs = self.rag.retrieve(
                query,
                top_k=5,
                thread_id=None,
                stage=stage,
                prefer_agent=True,
                chat_history=None,
            )
            agent_msgs = []
            for d in docs:
                if (d.get("role") or "").lower() == "agent":
                    agent_msgs.append((d.get("clean_text") or d.get("text") or "").strip())
            notes = _analyze_messages(agent_msgs[:5])
            if not notes:
                return ""
            bullets = "\n- ".join(notes)
            return (
                "ASHANTI STYLE NOTES (tone only):\n"
                f"- {bullets}"
            )
        except Exception:
            return ""


