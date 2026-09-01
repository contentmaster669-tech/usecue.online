"""Detection formatting. Silence is the product.

These tests assert emptiness EXPLICITLY (== "") rather than falsiness,
because a "looks good" message would also be falsy under `not result` in
some refactors but would be a product failure.
"""

from callyr.detection.engine import UPGRADE_REWRITE, format_detection
from callyr.detection.schema import Detection
from prompts.master_detection_prompt import WARNING_ICON


def _clean() -> Detection:
    return Detection(detected=False, problem_type="none")


def _flagged(**kw) -> Detection:
    base = {
        "detected": True,
        "problem_type": "sycophancy",
        "alert_line": "The response agreed without examining your premise.",
        "better_prompt": "Challenge my assumption and cite sources.",
    }
    base.update(kw)
    return Detection(**base)


class TestSilence:
    def test_clean_returns_empty_string(self):
        assert format_detection(_clean(), include_rewrite=True) == ""

    def test_failed_call_returns_empty_string(self):
        # None is what openai_client returns on timeout/error. Indistinguishable
        # from "nothing detected", by design.
        assert format_detection(None, include_rewrite=True) == ""

    def test_flagged_with_blank_alert_stays_silent(self):
        # Nothing useful to show; a bare warning icon would be worse than silence.
        assert format_detection(_flagged(alert_line="  "), include_rewrite=True) == ""


class TestFlagged:
    def test_includes_icon_alert_and_rewrite(self):
        out = format_detection(_flagged(), include_rewrite=True)
        assert out.startswith(WARNING_ICON)
        assert "agreed without examining" in out
        assert "Challenge my assumption" in out

    def test_rewrite_is_quoted_on_its_own_line(self):
        out = format_detection(_flagged(), include_rewrite=True)
        assert '"Challenge my assumption and cite sources."' in out.splitlines()

    def test_output_is_short(self):
        # Two-line output is the contract; guard against creeping verbosity.
        assert len(format_detection(_flagged(), include_rewrite=True).splitlines()) <= 3


class TestAlertWithoutRewrite:
    """Free tier: detection quota left, rewrite quota exhausted."""

    def test_alert_shown_with_upgrade_nudge(self):
        out = format_detection(_flagged(), include_rewrite=False)
        assert "agreed without examining" in out
        assert UPGRADE_REWRITE in out

    def test_rewrite_is_withheld(self):
        out = format_detection(_flagged(), include_rewrite=False)
        assert "Challenge my assumption" not in out

    def test_never_silently_incomplete(self):
        # The user must always understand why there is an alert but no prompt.
        out = format_detection(_flagged(), include_rewrite=False)
        assert out.strip().endswith(UPGRADE_REWRITE)

    def test_missing_rewrite_falls_back_to_nudge(self):
        # Model flagged but produced no rewrite: don't emit a dangling label.
        out = format_detection(_flagged(better_prompt=""), include_rewrite=True)
        assert UPGRADE_REWRITE in out
        assert "Ye prompt try karo" not in out
