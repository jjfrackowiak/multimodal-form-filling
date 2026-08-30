from __future__ import annotations

from pathlib import Path

import yaml

from cv.schema import ParsedChecklist, Requirement


def load_checklist(path: Path) -> ParsedChecklist:
    doc = yaml.safe_load(path.read_text()) or {}
    reqs: list[Requirement] = []
    for row in doc.get("requirements") or []:
        raw = row.get("constraint")
        if isinstance(raw, dict):
            constraint = raw.get("value") or raw.get("kind")
        elif isinstance(raw, str):
            constraint = raw
        else:
            constraint = None
        text = row.get("text") or ""
        if not isinstance(text, str):
            text = str(text)
        reqs.append(
            Requirement(
                id=str(row["id"]).strip(),
                text=text.strip(),
                source_span=str(row.get("source_span") or "").strip(),
                expected_count=int(row.get("expected_count") or 1),
                constraint=constraint,
            )
        )
    return ParsedChecklist(
        expected_total_photos=doc.get("expected_total_photos"),
        requirements=reqs,
    )


def spans_complete(checklist: ParsedChecklist) -> bool:
    """True when every requirement has a unique id and non-empty text.

    `text` is the look-for. `source_span` is optional provenance and is not required.
    """
    reqs = checklist.requirements
    if not reqs:
        return False
    ids = [r.id for r in reqs if r.id]
    if len(ids) != len(reqs) or len(set(ids)) != len(reqs):
        return False
    return all(r.text.strip() for r in reqs)
