
import re
from typing import Any


def analyze_transcript(transcript: str) -> dict[str, Any]:
    """Extract draft SOW information from a meeting transcript."""

    if not transcript or not transcript.strip():
        raise ValueError("Transcript cannot be empty.")

    lines = [
        line.strip()
        for line in transcript.splitlines()
        if line.strip()
    ]

    deliverables = []
    assumptions = []
    exclusions = []
    open_questions = []
    scope_items = []

    for line in lines:
        lower = line.lower()

        item = {
            "text": line,
            "source": line,
        }

        is_excluded = bool(
            re.search(
                r"\b(out of scope|excluded|not included|"
                r"won't include|will not include)\b",
                lower,
            )
        )

        is_question = (
            "?" in line
            or bool(
                re.search(
                    r"\b(open question|need to confirm|unclear|"
                    r"tbd|to be decided|not sure)\b",
                    lower,
                )
            )
        )

        if re.search(
            r"\b(deliver|provide|build|develop|create|implement|integrate)\b",
            lower,
        ) and not is_excluded and not is_question:
            deliverables.append(item)

        if re.search(
            r"\b(assume|assuming|we expect|provided that|if available)\b",
            lower,
        ):
            assumptions.append(item)

        if is_excluded:
            exclusions.append(item)

        if is_question:
            open_questions.append(item)

        if (
            re.search(
                r"\b(scope|requirement|feature|functionality|must have|"
                r"needs to|we need|need a|needs a|should have|would like|"
                r"customer portal|invoice downloads|login)\b",
                lower,
            )
            and not is_excluded
            and not is_question
        ):
            scope_items.append(item)

    return {
        "status": "draft",
        "scope": scope_items,
        "deliverables": deliverables,
        "assumptions": assumptions,
        "exclusions": exclusions,
        "open_questions": open_questions,
        "review_required": True,
        "notes": [
            "Rule-based extraction only; validate every item against the source transcript.",
            "Items may appear in multiple sections and require human review.",
            "No timeline, cost, or effort estimate has been inferred.",
        ],
    }
