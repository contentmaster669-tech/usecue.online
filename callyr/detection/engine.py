"""Formats a Detection into the PART 4 output shape.

Silence is the product: when nothing is detected this returns "" -- an empty
string, not a "looks good" message. Callers must treat "" as success.
"""

from callyr.detection.schema import Detection
from prompts.master_detection_prompt import WARNING_ICON

UPGRADE_REWRITE = "Upgrade to Pro for the rewritten prompt."
LIMIT_REACHED = "Cue daily limit reached — upgrade for unlimited."

CLEAN_ICON = "✓"
CLEAN_LINE = f"{CLEAN_ICON} Cue — no sycophancy or hallucination detected."

# The rewrite is a suggestion, never an instruction. This label is what keeps
# the host model from treating better_prompt as something to act on itself.
REWRITE_LABEL = "Optional — a sharper way to ask:"


def format_detection(detection: Detection | None, *, include_rewrite: bool) -> str:
    """Render a detection as user-facing text.

    A clean result now renders CLEAN_LINE rather than "" -- Cue is visibly
    active on every checked message. Note this deliberately overrides the
    master prompt's PART 4 ("Bilkul chup raho. Zero output."): PART 4 remains
    the semantic contract for the MODEL, which still reports detected=false
    through the schema; presentation is decided here. The prompt is verbatim
    and must not be edited to match.

    "" is now reserved for the cases where Cue genuinely cannot speak: a
    failed call, an unknown key, an unreachable database, or exhausted quota.
    Those stay indistinguishable from each other by design.

    include_rewrite=False is the alert-without-rewrite quota state: the user
    has detection quota left but has exhausted their daily rewrites.
    """
    if detection is None:
        # Timeout, API error, or malformed output. Fail silent -- never surface
        # an error into the user's conversation.
        return ""

    if not detection.detected:
        return CLEAN_LINE

    alert = detection.alert_line.strip()
    if not alert:
        # Flagged but gave no alert text. Reporting a problem we cannot name
        # would be worse than reporting none, so fall back to the clean line
        # rather than emit a bare icon.
        return CLEAN_LINE

    lines = [f"{WARNING_ICON} {alert}"]

    rewrite = detection.better_prompt.strip()
    if include_rewrite and rewrite:
        lines.append(REWRITE_LABEL)
        lines.append(f'"{rewrite}"')
    else:
        lines.append(UPGRADE_REWRITE)

    return "\n".join(lines)
