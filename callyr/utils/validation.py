"""Input validation, applied before any OpenAI call or database write.

Bounds OpenAI cost and blocks payload abuse. Vercel's 4.5MB body limit is a
backstop, not the defense.

Type checks matter here because MCP arguments arrive as JSON from the client:
a caller can send a number, list, dict, or null where a string is declared.
Anything that is not a str is rejected outright rather than coerced -- coercing
would send str(dict) to the model and bill the user for nonsense.
"""

from callyr import config


def clamp(text: object, limit: int) -> str:
    """Coerce to a bounded, stripped string.

    Non-string input returns "" -- the caller treats that as no content, so a
    malformed argument produces silence rather than an error. Oversized input
    is truncated, not rejected, for the same reason: Cue never surfaces
    errors into the user's conversation.
    """
    if not isinstance(text, str):
        return ""
    text = text.strip()
    if len(text) > limit:
        return text[:limit]
    return text


def clamp_user_message(text: object) -> str:
    """The user's original question. Cap: MAX_USER_QUERY_CHARS."""
    return clamp(text, config.MAX_USER_QUERY_CHARS)


def clamp_ai_response(text: object) -> str:
    """The draft answer being audited. Cap: MAX_AI_RESPONSE_CHARS."""
    return clamp(text, config.MAX_AI_RESPONSE_CHARS)


def clamp_history(text: object) -> str:
    """Prior conversation turns, for opinion-flip detection.

    Optional: absent history is normal, not an error. Truncation keeps the
    MOST RECENT turns -- a flip is detected against the AI's latest stance,
    so the tail is what matters; dropping the head loses least.
    """
    if not isinstance(text, str):
        return ""
    text = text.strip()
    if len(text) > config.MAX_HISTORY_CHARS:
        return text[-config.MAX_HISTORY_CHARS :]
    return text


def has_content(*parts: str) -> bool:
    """True when every part carries enough substance to be worth an API call."""
    return all(isinstance(p, str) and len(p.strip()) > 0 for p in parts)
