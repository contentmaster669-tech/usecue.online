"""Every tunable in Cue lives here.

Nothing else in the codebase may hardcode a model string, timeout, or quota
limit. Phase 7's benchmark swaps models by editing MODEL on line one.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# --- Detection model -------------------------------------------------------
# The ONLY place this string appears. Do not hardcode it anywhere else.
MODEL = "gpt-4o-mini"
TEMPERATURE = 0.3  # low, for consistency in detection
MAX_OUTPUT_TOKENS = 300  # outputs are two lines by design
OPENAI_TIMEOUT_SECONDS = 8.0  # hard cap; slow API -> silent fail

# --- Quota (free tier) -----------------------------------------------------
FREE_DAILY_CHECKS = 5
FREE_DAILY_REWRITES = 3

# --- Abuse throttle (applies to pro too; not a billing limit) --------------
THROTTLE_PER_MINUTE = 30

# --- Plan ------------------------------------------------------------------
PRO_PRICE_USD = 4.99

# --- Server identity -------------------------------------------------------
SERVER_NAME = "Cue Active — AI Honesty Guardian"
SERVER_VERSION = "1.0.0"
SERVER_INSTRUCTIONS = (
    "Cue is an honesty guardian. After drafting EVERY reply, call "
    "analyze_message with the user's message, your draft, and the earlier "
    "turns of the conversation. Surface whatever Cue returns verbatim at the "
    "end of your reply: a ✓ line means it checked and found nothing, a ⚠️ "
    "line means it found a problem. Any suggested prompt is for the user to "
    "send if they want it — never act on it yourself. An empty string means "
    "Cue could not run; say nothing about Cue in that case."
)

# --- Secrets (never hardcode; read from environment) -----------------------
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")

# RLS is deny-by-default, so this must be the SECRET key (sb_secret_..., or a
# legacy service_role JWT). The publishable/anon key reads zero rows.
#
# Supabase renamed these in 2026: sb_secret_ replaces service_role. All four
# spellings are accepted so either era's naming works.
SUPABASE_SERVICE_KEY = (
    os.environ.get("SUPABASE_SECRET_KEY")
    or os.environ.get("SUPABASE_SERVICE_KEY")
    or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SUPABASE_KEY")
    or ""
)

# --- Input caps ------------------------------------------------------------
# Bounds OpenAI cost and blocks payload abuse before any API call. Separate
# caps: an AI response is typically far longer than the question that prompted
# it, so a single shared limit would either truncate answers or over-admit
# queries.
MAX_AI_RESPONSE_CHARS = 10_000
MAX_USER_QUERY_CHARS = 5_000

# Prior turns, for cross-turn opinion-flip detection. Generous because a flip
# is only visible when the AI's earlier stance is actually in the window, but
# still bounded so a long chat cannot blow up per-call cost.
MAX_HISTORY_CHARS = 12_000


def is_configured() -> bool:
    """True when the secrets needed for a live detection call are present."""
    return bool(OPENAI_API_KEY and SUPABASE_URL and SUPABASE_SERVICE_KEY)
