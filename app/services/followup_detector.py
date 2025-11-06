from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, Optional


logger = logging.getLogger(__name__)


def _normalize_text(text: str) -> str:
    """Lowercase and normalize common apostrophes/spaces for robust matching."""
    if not isinstance(text, str):
        return ""
    normalized = text.strip().lower()
    # Normalize smart quotes/apostrophes
    normalized = (
        normalized.replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )
    # Collapse excessive whitespace
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


class FollowUpPromiseDetector:
    """Detects whether an assistant promises to follow up.

    Hybrid approach: pattern-based first, then optional LLM fallback.

    detect(text, llm) -> {
        "is_followup": bool,
        "confidence": float,  # 0..1
        "phrase": Optional[str],  # matched phrase if any
    }
    """

    # Precompile weighted patterns for common follow-up promises.
    _PATTERNS: list[tuple[re.Pattern[str], float]] = []

    # Build patterns once at class load time.
    followup_phrases = [
        # Strong/explicit commitments
        (r"\b(i|we)'?ll\s+get\s+back\s+to\s+you\b", 0.95),
        (r"\b(i|we)\s+will\s+get\s+back\s+to\s+you\b", 0.95),
        (r"\b(get|getting)\s+back\s+to\s+you\b", 0.9),
        (r"\b(i|we)'?ll\s+follow[- ]?up\b", 0.9),
        (r"\b(i|we)\s+will\s+follow[- ]?up\b", 0.9),
        (r"\bfollow[- ]?up\s+(shortly|soon|tomorrow|later|with\s+details)\b", 0.9),
        (r"\b(i|we)'?ll\s+confirm\b", 0.8),
        (r"\b(i|we)'?ll\s+confirm.*?get\s+back\b", 0.95),
        (r"\b(i|we)'?ll\s+check.*?get\s+back\b", 0.95),
        (r"\b(i|we)'?ll\s+update\s+you\b", 0.85),
        (r"\b(i|we)'?ll\s+let\s+you\s+know\b", 0.85),
        (r"\bcircle\s+back\b", 0.85),
        (r"\btouch\s+base\b", 0.75),
        (r"\breach\s+out\b", 0.75),
        (r"\bcheck\s+in\b", 0.75),
        # Variants without subject but clearly future commitment
        (r"\bwill\s+follow[- ]?up\b", 0.85),
        (r"\bwill\s+get\s+back\b", 0.9),
    ]

    for pattern, weight in followup_phrases:
        _PATTERNS.append((re.compile(pattern, re.IGNORECASE), weight))

    def detect(self, text: str, llm: Optional[Callable[[str], Any]] = None) -> Dict[str, Any]:
        normalized = _normalize_text(text or "")

        # Pattern-based detection
        best_match: Optional[tuple[str, float]] = None
        for regex, weight in self._PATTERNS:
            match = regex.search(normalized)
            if match:
                phrase = match.group(0)
                if not best_match or weight > best_match[1]:
                    best_match = (phrase, weight)

        if best_match:
            phrase, confidence = best_match
            logger.debug(
                "followup_detector.pattern_match",
                extra={"phrase": phrase, "confidence": confidence},
            )
            return {"is_followup": True, "confidence": float(confidence), "phrase": phrase}

        # Optional LLM fallback
        if llm is not None and normalized:
            try:
                prompt = (
                    "You classify if the ASSISTANT promises to follow up (future commitment) in the text.\n"
                    "Return strict JSON: {\"is_followup\": bool, \"confidence\": number 0..1}.\n"
                    "Examples: \n"
                    "- 'I'll get back to you tomorrow.' -> {\"is_followup\": true, \"confidence\": 0.95}\n"
                    "- 'Let me know if you need anything.' -> {\"is_followup\": false, \"confidence\": 0.2}\n"
                    f"Text: {text}\n"
                )
                llm_result = llm(prompt)
                if isinstance(llm_result, str):
                    parsed = json.loads(llm_result)
                else:
                    parsed = llm_result  # assume already dict-like

                is_followup = bool(parsed.get("is_followup"))
                confidence = float(parsed.get("confidence", 0.0))
                if is_followup and confidence > 0.5:
                    logger.debug(
                        "followup_detector.llm_match",
                        extra={"confidence": confidence},
                    )
                    return {
                        "is_followup": True,
                        "confidence": confidence,
                        "phrase": None,
                    }
            except Exception as exc:  # noqa: BLE001
                logger.warning("followup_detector.llm_fallback_error: %s", exc)

        return {"is_followup": False, "confidence": 0.0, "phrase": None}



