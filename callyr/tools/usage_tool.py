"""check_usage -- remaining daily quota for the calling user.

Reads quota without consuming any. One database read, no OpenAI call.
"""

import logging

from callyr.auth.context import get_api_key
from callyr.db import usage
from callyr.db.users import resolve_user_id

log = logging.getLogger("callyr.check_usage")

NOT_CONNECTED = (
    "Cue is not linked to an account. Add your Cue URL with its API key "
    "in your app's connector settings."
)
UNAVAILABLE = "Cue usage is temporarily unavailable. Detection is unaffected."
THROTTLED = "Cue is receiving too many requests. Try again in a moment."


TOOL_DESCRIPTION = (
    "Show how many Cue honesty checks and prompt rewrites the user "
    "has left today, and which plan they are on. Consumes no quota."
)


async def check_usage() -> str:
    """Report the caller's plan and remaining daily quota.

    Module-level so it stays directly callable and testable; register() only
    wraps it for MCP.
    """
    user_id = await resolve_user_id(get_api_key())
    if user_id is None:
        return NOT_CONNECTED

    state = await usage.get_quota(user_id)
    if not state.ok:
        return UNAVAILABLE

    # Same abuse throttle as analyze_message. This tool hits the database, so
    # an unthrottled loop here is still a usable amplification vector.
    if state.throttled:
        return THROTTLED

    return f"Cue — {usage.free_tier_summary(state)}"


def register(mcp) -> None:
    mcp.tool(name="check_usage", description=TOOL_DESCRIPTION)(check_usage)
