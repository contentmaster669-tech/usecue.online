"""Formats a Detection into the PART 4 output shape.

Silence is the product: when nothing is detected this returns "" -- an empty
string, not a "looks good" message. Callers must treat "" as success.
"""

from callyr.detection.schema import Detection
from prompts.master_detection_prompt import WARNING_ICON

UPGRADE_REWRITE = "Upgrade to Pro for the rewritten prompt."
LIMIT_REACHED = "Cue daily limit reached — upgrade for unlimited."


def format_detection(detection: Detection | None, *, include_rewrite: bool) -> str:
    """Render a detection as user-facing text.

    Returns "" when nothing was detected or the call failed -- these are
    deliberately indistinguishable to the user.

    include_rewrite=False is the alert-without-rewrite quota state: the user
    has detection quota left but has exhausted their daily rewrites.
    """
    if detection is None or not detection.detected:
        return ""

    alert = detection.alert_line.strip()
    if not alert:
        # Model flagged a problem but gave no alert text; nothing useful to
        # show, so stay silent rather than emit a bare icon.
        return ""

    lines = [f"{WARNING_ICON} {alert}"]

    rewrite = detection.better_prompt.strip()
    if include_rewrite and rewrite:
        lines.append("Ye prompt try karo:")
        lines.append(f'"{rewrite}"')
    else:
        lines.append(UPGRADE_REWRITE)

    return "\n".join(lines)
