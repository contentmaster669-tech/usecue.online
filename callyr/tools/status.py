"""cue_status -- the Active Indicator.

Its EXISTENCE in the client's tools panel is the indicator. Anthropic's
connector UI does not render serverInfo, so a tool is the only reliable
signal. Calling it is optional confirmation.

Zero API calls. Zero database reads. Static string only.
"""

STATUS_LINE = "Cue Active — Monitoring for sycophancy and hallucination in real-time."

TOOL_DESCRIPTION = (
    "Cue Active — AI Honesty Guardian. Confirms Cue is connected and "
    "monitoring this conversation for sycophancy and hallucination. Returns a "
    "status line instantly; makes no API calls and consumes no quota."
)


async def cue_status() -> str:
    """Confirm Cue is connected and active.

    Module-level so it stays directly callable and testable; register() only
    wraps it for MCP.
    """
    return STATUS_LINE


def register(mcp) -> None:
    mcp.tool(name="cue_status", description=TOOL_DESCRIPTION)(cue_status)
