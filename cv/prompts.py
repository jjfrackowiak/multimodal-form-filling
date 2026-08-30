"""Prompt for one photo. Checklist is injected; no frozen car taxonomy."""

from __future__ import annotations

from cv.schema import Requirement


def label_prompt(requirements: list[Requirement], manifest_text: str | None) -> str:
    lines = [
        "Label this inspection photo against the checklist.",
        "hits[].id = checklist ids this photo actually supports (zero or more).",
        "If that id has a constraint, set hits[].constraint_ok from the pixels",
        "and hits[].constraint_evidence. Different ids on the same photo may differ.",
        "findings[]: every useful visible detail (lamps, readings, plate, damage).",
        "",
        "Checklist:",
    ]
    for r in requirements:
        extra = f" | constraint: {r.constraint}" if r.constraint else ""
        span = f' | source: "{r.source_span}"' if r.source_span else ""
        lines.append(f"- {r.id}: {r.text} (need {r.expected_count}){extra}{span}")
    if manifest_text and manifest_text.strip():
        lines.append("")
        lines.append("Client shot list (what they say they sent):")
        lines.append(manifest_text.strip())
    return "\n".join(lines)
