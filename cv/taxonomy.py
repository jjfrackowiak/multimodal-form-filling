"""Prompts. Look-fors come from expected_requirements; the manifest lists what was sent."""


def label_task(requirements: list, manifest_text: str | None) -> str:
    lines = [
        "This photo is part of a vehicle-return submission.",
        "The checklist is what information must be extracted from the photos.",
        "Tag the photo with requirement ids from the checklist that it actually supports.",
        "A photo may satisfy more than one id, or none.",
        "If a tagged requirement has a constraint, set constraint_ok and pose_evidence.",
        "Cite odometer_km, warnings, registration in the typed fields when visible.",
        "",
        "Checklist (extract these):",
    ]
    for r in requirements:
        extra = f"  constraint: {r.constraint}" if getattr(r, "constraint", None) else ""
        span = f'  source: "{r.source_span}"' if getattr(r, "source_span", None) else ""
        lines.append(f"- {r.id}: {r.text} (need {r.expected_count}){extra}{span}")
    if manifest_text and manifest_text.strip():
        lines.append("")
        lines.append("Client manifest (images they claim to have sent):")
        lines.append(manifest_text.strip())
    return "\n".join(lines)
