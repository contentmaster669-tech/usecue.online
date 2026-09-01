"""analyze_message -- the core detection tool.

Order of operations matters for cost: identity -> quota -> OpenAI. A user who
is out of quota never reaches the API call.

The tool description is the mechanism that drives near-passive operation. MCP
is a pull protocol with no per-message hook, so this text is the only thing
persuading the host model to self-audit.
"""

import logging

from callyr.auth.context import get_api_key
from callyr.db import usage
from callyr.db.users import resolve_user_id
from callyr.detection import openai_client
from callyr.detection.engine import LIMIT_REACHED, format_detection
from callyr.utils.validation import (
    clamp_ai_response,
    clamp_history,
    clamp_user_message,
    has_content,
)

log = logging.getLogger("callyr.analyze")

TOOL_DESCRIPTION = (
    "Cue honesty check. Before finalizing a reply, call this with the "
    "user's message and your draft response to check it for sycophancy "
    "(agreeing to please rather than to inform) and hallucination "
    "(confident claims without support).\n\n"
    "IMPORTANT: also pass conversation_history with the earlier turns of this "
    "conversation whenever any exist. Cue's highest-priority check is the "
    "opinion flip — whether your current answer reverses a position you took "
    "earlier because the user pushed back, rather than because of new "
    "evidence. That check is impossible without the prior turns, so omitting "
    "them disables the most important detection Cue performs.\n\n"
    "If Cue returns text, show it to the user verbatim. If it returns an "
    "empty string, nothing was detected — say nothing about Cue and "
    "deliver your reply unchanged. Silence is the normal result."
)


async def analyze_message(
    user_message: str, ai_response: str, conversation_history: str = ""
) -> str:
    """Check a draft AI response for sycophancy and hallucination.

    Module-level so it is directly callable and testable. register() below
    only wraps it for MCP -- tools/ stays a thin surface with no logic of
    its own.

    Args:
        user_message: What the user originally asked.
        ai_response: The draft answer being audited.
        conversation_history: Earlier turns, if any. Optional, but without it
            the cross-turn opinion-flip check cannot run -- that is the
            highest-priority pattern in the master prompt.

    Returns:
        Alert plus a rewritten prompt if a problem was found, otherwise
        an empty string.
    """
    # Type-check and bound before anything else. Non-string arguments (a client
    # can send any JSON type) become "" and short-circuit below.
    user_message = clamp_user_message(user_message)
    ai_response = clamp_ai_response(ai_response)
    # History is optional: absent is normal, so it is not part of has_content.
    conversation_history = clamp_history(conversation_history)
    if not has_content(user_message, ai_response):
        return ""

    user_id = await resolve_user_id(get_api_key())
    if user_id is None:
        # Unknown or revoked key. Stay silent rather than leak auth state
        # into the user's conversation.
        log.warning("analyze_message called with unresolvable API key")
        return ""

    state = await usage.get_quota(user_id)
    if not state.ok:
        return ""  # database unreachable -> silence, same as no detection

    # Abuse throttle. Applies to pro too; not a billing limit.
    if state.throttled:
        return ""

    # Out of detection quota: do NOT call OpenAI. This is the cost saver.
    if not state.has_check:
        if await usage.should_show_limit_notice(user_id):
            return LIMIT_REACHED
        return ""

    detection = await openai_client.detect(
        user_message, ai_response, conversation_history
    )

    # Only spend quota on a call that actually completed. A failed call
    # returns None and must not bill the user a check.
    if detection is None:
        return ""

    after_check = await usage.consume(user_id, usage.CHECK)

    # A rewrite is only produced when one was detected AND rewrite quota
    # remains. Otherwise the alert still shows, with an upgrade nudge.
    include_rewrite = True
    if detection.detected and not after_check.is_pro:
        if after_check.has_rewrite:
            await usage.consume(user_id, usage.REWRITE)
        else:
            include_rewrite = False

    return format_detection(detection, include_rewrite=include_rewrite)


def register(mcp) -> None:
    mcp.tool(name="analyze_message", description=TOOL_DESCRIPTION)(analyze_message)
