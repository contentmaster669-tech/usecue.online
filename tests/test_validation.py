"""Input validation: separate caps, and type safety against hostile arguments.

MCP arguments arrive as JSON from the client, so a caller can send any type
where a string is declared. Nothing here may raise -- Cue never surfaces
errors into the conversation.
"""

from callyr import config
from callyr.utils.validation import (
    clamp_ai_response,
    clamp_user_message,
    has_content,
)


class TestSeparateCaps:
    def test_caps_are_as_specified(self):
        assert config.MAX_AI_RESPONSE_CHARS == 10_000
        assert config.MAX_USER_QUERY_CHARS == 5_000

    def test_ai_response_truncated_at_10k(self):
        assert len(clamp_ai_response("x" * 50_000)) == 10_000

    def test_user_query_truncated_at_5k(self):
        assert len(clamp_user_message("x" * 50_000)) == 5_000

    def test_under_cap_passes_through(self):
        assert clamp_ai_response("hello") == "hello"
        assert clamp_user_message("hello") == "hello"

    def test_whitespace_is_stripped(self):
        assert clamp_user_message("  hi  ") == "hi"


class TestTypeSafety:
    """A hostile or buggy client can send any JSON type."""

    def test_non_string_types_become_empty(self):
        for bad in [None, 123, 4.5, True, [], {}, ["a"], {"k": "v"}, object()]:
            assert clamp_ai_response(bad) == ""
            assert clamp_user_message(bad) == ""

    def test_no_type_ever_raises(self):
        for bad in [None, 0, [], {}, set(), b"bytes"]:
            clamp_ai_response(bad)
            clamp_user_message(bad)

    def test_has_content_rejects_non_strings(self):
        assert not has_content(None, "ok")
        assert not has_content(123, "ok")
        assert not has_content("", "ok")
        assert not has_content("   ", "ok")
        assert has_content("a", "b")


class TestOversizeDoesNotReachOpenAI:
    """Truncation happens before the API call, so cost stays bounded."""

    async def test_giant_payload_is_bounded(self, monkeypatch):
        from callyr.db import usage as usage_mod
        from callyr.db.usage import QuotaState
        from callyr.detection import openai_client
        from callyr.tools import analyze

        seen = {}

        async def capture(user_message, ai_response, conversation_history=""):
            seen["user"] = len(user_message)
            seen["ai"] = len(ai_response)

        async def fake_resolve(_key):
            return "user-1"

        async def full_quota(_uid):
            return QuotaState(plan="free", checks_left=5, rewrites_left=3)

        monkeypatch.setattr(openai_client, "detect", capture)
        monkeypatch.setattr(analyze, "resolve_user_id", fake_resolve)
        monkeypatch.setattr(usage_mod, "get_quota", full_quota)

        await analyze.analyze_message(user_message="u" * 999_999, ai_response="a" * 999_999)
        assert seen["user"] == 5_000
        assert seen["ai"] == 10_000


class TestHistory:
    """conversation_history enables the cross-turn opinion-flip check."""

    def test_optional_absent_is_normal(self):
        from callyr.utils.validation import clamp_history

        assert clamp_history("") == ""
        assert clamp_history(None) == ""

    def test_non_string_types_become_empty(self):
        from callyr.utils.validation import clamp_history

        for bad in [123, [], {}, True, object()]:
            assert clamp_history(bad) == ""

    def test_truncation_keeps_the_most_recent_turns(self):
        """A flip is judged against the AI's latest stance, so the tail is
        what matters -- dropping the head loses least."""
        from callyr.utils.validation import clamp_history

        text = "OLDEST" + ("x" * config.MAX_HISTORY_CHARS) + "NEWEST"
        out = clamp_history(text)
        assert len(out) == config.MAX_HISTORY_CHARS
        assert out.endswith("NEWEST")
        assert "OLDEST" not in out

    async def test_history_reaches_the_detector(self, monkeypatch):
        from callyr.db import usage as usage_mod
        from callyr.db.usage import QuotaState
        from callyr.detection import openai_client
        from callyr.tools import analyze

        seen = {}

        async def capture(user_message, ai_response, conversation_history=""):
            seen["history"] = conversation_history

        async def fake_resolve(_key):
            return "user-1"

        async def full_quota(_uid):
            return QuotaState(plan="free", checks_left=5, rewrites_left=3)

        monkeypatch.setattr(openai_client, "detect", capture)
        monkeypatch.setattr(analyze, "resolve_user_id", fake_resolve)
        monkeypatch.setattr(usage_mod, "get_quota", full_quota)

        await analyze.analyze_message(
            user_message="are you sure?",
            ai_response="You're right, I was wrong.",
            conversation_history="AI: X is correct.\nUser: I disagree.",
        )
        assert "I disagree" in seen["history"]


class TestPromptInput:
    """The assembled input block keeps untrusted fields separately tagged."""

    def test_history_is_tagged_and_comes_first(self):
        from callyr.detection.openai_client import _build_input

        out = _build_input("q", "a", "prior turns")
        assert "<conversation_history>" in out
        assert out.index("<conversation_history>") < out.index("<ai_response>")

    def test_history_omitted_when_absent(self):
        from callyr.detection.openai_client import _build_input

        out = _build_input("q", "a", "")
        assert "<conversation_history>" not in out
        assert "<user_message>" in out and "<ai_response>" in out
