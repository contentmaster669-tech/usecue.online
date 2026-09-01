"""Quota resolution and consumption.

Increments happen in Postgres via the consume_quota RPC, not here. Doing the
read-then-write in application code creates a race where two concurrent MCP
calls both read "1 left" and both proceed.

Daily reset needs no cron: daily_usage is keyed (user_id, usage_date), so a
new day is simply a new row and yesterday's row goes inert.
"""

import logging
from dataclasses import dataclass

from callyr import config
from callyr.db.client import get_client

log = logging.getLogger("callyr.usage")

CHECK = "check"
REWRITE = "rewrite"


@dataclass
class QuotaState:
    """What the caller is allowed to do right now."""

    plan: str  # "free" | "pro"
    checks_left: int  # -1 means unlimited
    rewrites_left: int  # -1 means unlimited
    throttled: bool = False  # per-minute abuse throttle tripped
    ok: bool = True  # False when the DB could not be reached

    @property
    def is_pro(self) -> bool:
        return self.plan == "pro"

    @property
    def has_check(self) -> bool:
        return self.checks_left != 0

    @property
    def has_rewrite(self) -> bool:
        return self.rewrites_left != 0


async def get_quota(user_id: str) -> QuotaState:
    """Read current plan and remaining quota without consuming any."""
    client = await get_client()
    if client is None:
        return QuotaState(plan="free", checks_left=0, rewrites_left=0, ok=False)
    try:
        result = await client.rpc("get_quota", {"p_user_id": user_id}).execute()
        row = result.data[0] if result.data else {}
        return QuotaState(
            plan=row.get("plan", "free"),
            checks_left=row.get("checks_left", 0),
            rewrites_left=row.get("rewrites_left", 0),
            throttled=row.get("throttled", False),
        )
    except Exception:
        log.exception("get_quota failed for user")
        return QuotaState(plan="free", checks_left=0, rewrites_left=0, ok=False)


async def consume(user_id: str, kind: str) -> QuotaState:
    """Atomically consume one unit of quota and return the new state.

    kind is CHECK or REWRITE. The RPC upserts today's row and increments
    under a single lock, so concurrent callers cannot both spend the last unit.
    """
    client = await get_client()
    if client is None:
        return QuotaState(plan="free", checks_left=0, rewrites_left=0, ok=False)
    try:
        result = await client.rpc("consume_quota", {"p_user_id": user_id, "p_kind": kind}).execute()
        row = result.data[0] if result.data else {}
        return QuotaState(
            plan=row.get("plan", "free"),
            checks_left=row.get("checks_left", 0),
            rewrites_left=row.get("rewrites_left", 0),
            throttled=row.get("throttled", False),
        )
    except Exception:
        log.exception("consume_quota failed for user")
        return QuotaState(plan="free", checks_left=0, rewrites_left=0, ok=False)


async def should_show_limit_notice(user_id: str) -> bool:
    """True at most once per day, the first time the user hits their cap.

    Tracked by limit_notice_shown_on so the upgrade line never becomes a nag.
    """
    client = await get_client()
    if client is None:
        return False
    try:
        result = await client.rpc("claim_limit_notice", {"p_user_id": user_id}).execute()
        return bool(result.data)
    except Exception:
        log.exception("claim_limit_notice failed for user")
        return False


def free_tier_summary(state: QuotaState) -> str:
    """Human-readable quota line for check_usage / cue_status."""
    if state.is_pro:
        return "Pro — unlimited checks and rewrites."
    return (
        f"Free — {max(state.checks_left, 0)}/{config.FREE_DAILY_CHECKS} checks and "
        f"{max(state.rewrites_left, 0)}/{config.FREE_DAILY_REWRITES} rewrites left today."
    )
