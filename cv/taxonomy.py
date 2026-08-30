"""Prompt text. Look-fors are injected from the parsed manifest."""

PARSE_TASK = """
Parse this client manifest for a vehicle-return photo inspection.

Split into discrete, checkable requirements. Keep source_span as a verbatim
substring of the input (do not fix typos). Assign R-01, R-02, … in order.

If a later line qualifies an earlier item (e.g. how a photo must be framed),
attach that as constraint on the requirement it qualifies — do not drop it
and do not attach it to the wrong item.

If the client states a total photo count, fill expected_total_photos.
A repeated line may be two photos; prefer a reading that matches the stated total.
"""


def label_task(requirements: list) -> str:
    lines = [
        "This photo is part of a vehicle-return submission.",
        "Tag it with the requirement ids it actually shows (from the list below).",
        "A photo may satisfy more than one id, or none.",
        "If a tagged requirement has a constraint, set constraint_ok and pose_evidence.",
        "Cite odometer_km, warnings, registration in the typed fields when visible.",
        "",
        "Requirements:",
    ]
    for r in requirements:
        extra = f"  constraint: {r.constraint}" if getattr(r, "constraint", None) else ""
        lines.append(f"- {r.id}: {r.text} (need {r.expected_count}){extra}")
    return "\n".join(lines)
