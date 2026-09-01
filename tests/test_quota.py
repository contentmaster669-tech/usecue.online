"""The four quota states, plus the cost-saving guarantee.

The critical assertion here is test_exhausted_never_calls_openai: an
out-of-quota user must not reach the API at all.
"""

import pytest

from callyr.db.usage import QuotaState
from callyr.detection.engine import LIMIT_REACHED, UPGRADE_REWRITE
from callyr.detection.schema import Detection


def _state(**kw) -> QuotaState:
    base = {"plan": "free", "checks_left": 5, "rewrites_left": 3}
    base.update(kw)
    return QuotaState(**base)


class TestQuotaState:
    def test_free_with_quota_can_do_both(self):
        s = _state()
        assert s.has_check and s.has_rewrite and not s.is_pro

    def test_zero_means_exhausted(self):
        assert not _state(checks_left=0).has_check
        assert not _state(rewrites_left=0).has_rewrite

    def test_pro_is_unlimited(self):
        # -1 is the unlimited sentinel; it must read as "available", not as
        # a falsy leftover count.
        s = _state(plan="pro", checks_left=-1, rewrites_left=-1)
        assert s.is_pro and s.has_check and s.has_rewrite

    def test_db_failure_is_not_ok(self):
        assert not QuotaState(plan="free", checks_left=0, rewrites_left=0, ok=False).ok


class TestAnalyzeFlow:
    """analyze_message's decision path, with the DB and OpenAI stubbed."""

    @pytest.fixture
    def patched(self, monkeypatch):
        from callyr.db import usage as usage_mod
        from callyr.detection import openai_client
        from callyr.tools import analyze

        calls = {"openai": 0, "consumed": []}

        async def fake_detect(user_message, ai_response, conversation_history=""):
            calls["openai"] += 1
            return Detection(
                detected=True,
                problem_type="sycophancy",
                alert_line="Agreed without examining the premise.",
                better_prompt="Push back on my assumption.",
            )

        async def fake_resolve(_key):
            return "user-1"

        # analyze.py calls openai_client.detect(...) as a module attribute, so
        # patching the module is enough. resolve_user_id is imported by name,
        # so it must be patched on analyze itself.
        monkeypatch.setattr(openai_client, "detect", fake_detect)
        monkeypatch.setattr(analyze, "resolve_user_id", fake_resolve)

        async def fake_consume(user_id, kind):
            calls["consumed"].append(kind)
            return _state(checks_left=1, rewrites_left=1)

        monkeypatch.setattr(usage_mod, "consume", fake_consume)
        return calls, monkeypatch, usage_mod, analyze

    async def test_exhausted_never_calls_openai(self, patched):
        """The cost saver: no quota means no API spend."""
        calls, monkeypatch, usage_mod, analyze = patched

        async def no_quota(_uid):
            return _state(checks_left=0)

        async def claim(_uid):
            return True

        monkeypatch.setattr(usage_mod, "get_quota", no_quota)
        monkeypatch.setattr(usage_mod, "should_show_limit_notice", claim)

        out = await analyze.analyze_message(
            user_message="is my plan good?", ai_response="Yes, it's perfect!"
        )
        assert out == LIMIT_REACHED
        assert calls["openai"] == 0

    async def test_limit_notice_shows_once_then_silence(self, patched):
        calls, monkeypatch, usage_mod, analyze = patched
        shown = {"n": 0}

        async def no_quota(_uid):
            return _state(checks_left=0)

        async def claim_once(_uid):
            shown["n"] += 1
            return shown["n"] == 1

        monkeypatch.setattr(usage_mod, "get_quota", no_quota)
        monkeypatch.setattr(usage_mod, "should_show_limit_notice", claim_once)

        first = await analyze.analyze_message(user_message="a", ai_response="b")
        second = await analyze.analyze_message(user_message="a", ai_response="b")
        assert first == LIMIT_REACHED
        assert second == ""  # never a nag
        assert calls["openai"] == 0

    async def test_rewrite_exhausted_shows_alert_with_nudge(self, patched):
        calls, monkeypatch, usage_mod, analyze = patched

        async def checks_only(_uid):
            return _state(checks_left=2, rewrites_left=0)

        async def consume_no_rewrite(user_id, kind):
            calls["consumed"].append(kind)
            return _state(checks_left=1, rewrites_left=0)

        monkeypatch.setattr(usage_mod, "get_quota", checks_only)
        monkeypatch.setattr(usage_mod, "consume", consume_no_rewrite)

        out = await analyze.analyze_message(user_message="a", ai_response="b")
        assert UPGRADE_REWRITE in out
        assert "Push back on my assumption" not in out
        assert "rewrite" not in calls["consumed"]  # don't spend what isn't there

    async def test_db_down_is_silent(self, patched):
        calls, monkeypatch, usage_mod, analyze = patched

        async def down(_uid):
            return QuotaState(plan="free", checks_left=0, rewrites_left=0, ok=False)

        monkeypatch.setattr(usage_mod, "get_quota", down)
        out = await analyze.analyze_message(user_message="a", ai_response="b")
        assert out == ""
        assert calls["openai"] == 0

    async def test_empty_input_short_circuits(self, patched):
        calls, _, _, analyze = patched
        assert await analyze.analyze_message(user_message="", ai_response="") == ""
        assert calls["openai"] == 0


class TestThrottle(TestAnalyzeFlow):
    """Abuse throttle applies to every DB-touching tool, not just analyze.

    Inherits TestAnalyzeFlow's `patched` fixture.
    """

    async def test_analyze_blocked_when_throttled(self, patched):
        calls, monkeypatch, usage_mod, analyze = patched

        async def throttled(_uid):
            return QuotaState(plan="free", checks_left=5, rewrites_left=3, throttled=True)

        monkeypatch.setattr(usage_mod, "get_quota", throttled)
        out = await analyze.analyze_message(user_message="a", ai_response="b")
        assert out == ""
        assert calls["openai"] == 0  # throttle gates before any API spend

    async def test_check_usage_blocked_when_throttled(self, monkeypatch):
        from callyr.db import usage as usage_mod
        from callyr.tools import usage_tool

        async def fake_resolve(_key):
            return "user-1"

        async def throttled(_uid):
            return QuotaState(plan="free", checks_left=5, rewrites_left=3, throttled=True)

        monkeypatch.setattr(usage_tool, "resolve_user_id", fake_resolve)
        monkeypatch.setattr(usage_mod, "get_quota", throttled)

        out = await usage_tool.check_usage()
        assert out == usage_tool.THROTTLED
