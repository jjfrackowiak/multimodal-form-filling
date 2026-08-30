"""Prompts. Look-fors come from expected_requirements; the manifest lists what was sent."""


def label_task(requirements: list, manifest_text: str) -> str:
    lines = [
        "This photo is part of a vehicle-return submission.",
        "expected_requirements is the documentation checklist: information that must",
        "be extracted from the photos (what to look for).",
        "The manifest is the client's list of images they say they provided — not the checklist.",
        "Tag the photo with requirement ids from the checklist that it actually supports.",
        "A photo may satisfy more than one id, or none.",
        "If a tagged requirement has a constraint, set constraint_ok and pose_evidence.",
        "Cite odometer_km, warnings, registration in the typed fields when visible.",
        "",
        "Checklist (extract these):",
    ]
    for r in requirements:
        extra = f"  constraint: {r.constraint}" if getattr(r, "constraint", None) else ""
        lines.append(f"- {r.id}: {r.text} (need {r.expected_count}){extra}")
    lines.append("")
    lines.append("Client manifest (images they claim to have sent):")
    lines.append(manifest_text.strip())
    return "\n".join(lines)
