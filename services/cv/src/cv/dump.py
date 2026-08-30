from __future__ import annotations

import yaml

from cv.schema import Inventory


def inventory_to_yaml(inv: Inventory) -> str:
    images = []
    for im in inv.images:
        row: dict = {
            "file": im.file,
            "requirement_ids": im.requirement_ids,
            "hits": [h.model_dump(exclude_none=True) for h in im.hits],
        }
        if im.uri:
            row["uri"] = im.uri
        if im.note:
            row["note"] = im.note
        if im.findings:
            row["findings"] = [
                {k: v for k, v in f.model_dump().items() if v not in (None, "")}
                for f in im.findings
            ]
        if im.exact_duplicate_of:
            row["exact_duplicate_of"] = im.exact_duplicate_of
        images.append(row)
    doc = {
        "checklist": inv.checklist.model_dump(exclude_none=True),
        "images": images,
        "exact_duplicate_pairs": inv.exact_duplicate_pairs,
    }
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
