"""OpenAI Responses API wrapper. Fail-silent by contract.

Every failure mode -- timeout, rate limit, network error, malformed output,
unhandled exception -- returns None, which the engine renders as "".
The user never sees an error string from Cue.
"""

import logging

from openai import AsyncOpenAI

from callyr import config
from callyr.detection.schema import Detection
from prompts.master_detection_prompt import MASTER_DETECTION_PROMPT

log = logging.getLogger("callyr.openai")

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    """Lazily build the client so import never fails on a missing key."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=config.OPENAI_API_KEY,
            timeout=config.OPENAI_TIMEOUT_SECONDS,
            max_retries=0,  # the 8s cap is the whole budget; no retry behind it
        )
    return _client


def _build_input(user_message: str, ai_response: str, history: str) -> str:
    """Assemble the untrusted content block.

    Each field is wrapped in its own tag so the model can tell them apart.
    History comes first because the prompt's STEP ZERO checks for an opinion
    flip before any other pattern, and that check needs the AI's earlier
    stance in view.
    """
    parts = []
    if history:
        parts.append(f"<conversation_history>\n{history}\n</conversation_history>")
    parts.append(f"<user_message>\n{user_message}\n</user_message>")
    parts.append(f"<ai_response>\n{ai_response}\n</ai_response>")
    return "\n\n".join(parts)


async def detect(
    user_message: str, ai_response: str, conversation_history: str = ""
) -> Detection | None:
    """Run one detection pass. Returns None on any failure.

    conversation_history is optional prior turns; without it the model cannot
    verify a cross-turn reversal and the prompt tells it not to invent one.
    """
    try:
        response = await _get_client().responses.parse(
            model=config.MODEL,
            temperature=config.TEMPERATURE,
            max_output_tokens=config.MAX_OUTPUT_TOKENS,
            instructions=MASTER_DETECTION_PROMPT,
            # Untrusted content is passed as structured input, never
            # concatenated into the system prompt. The labels below are the
            # only framing; injected instructions inside them cannot redirect
            # the contract stated in the master prompt.
            input=[
                {
                    "role": "user",
                    "content": _build_input(
                        user_message, ai_response, conversation_history
                    ),
                }
            ],
            text_format=Detection,
        )
        return response.output_parsed
    except Exception:
        # Logged server-side, never surfaced into the conversation.
        log.exception("detection call failed; returning silence")
        return None
