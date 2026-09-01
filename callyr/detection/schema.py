"""The fixed output contract for detection.

The master prompt's PART 4 describes what to SAY (semantic contract); this
schema controls how it is DELIVERED. They look contradictory on purpose --
see the module docstring in prompts/master_detection_prompt.py.

Structured fields are what make the alert-without-rewrite quota state
expressible: the alert can be emitted while better_prompt is withheld and
replaced by an upgrade nudge. They also make silence a reliable boolean
rather than depending on the model returning a literally empty string.
"""

from typing import Literal

from pydantic import BaseModel, Field

ProblemType = Literal["sycophancy", "hallucination", "both", "none"]


class Detection(BaseModel):
    """Parsed result of one detection pass."""

    detected: bool = Field(description="True only if sycophancy or hallucination was found.")
    problem_type: ProblemType = Field(
        description="Which problem was found. 'none' when detected is false."
    )
    alert_line: str = Field(
        default="",
        description=(
            "One short sentence naming the problem, in the user's language. "
            "Empty when detected is false."
        ),
    )
    better_prompt: str = Field(
        default="",
        description=("One rewritten prompt in the user's language. Empty when detected is false."),
    )
