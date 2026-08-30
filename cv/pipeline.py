"""Editor-facing tool: build an inventory from checklist + photos."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from cv.checklist import load_checklist, spans_complete
from cv.images import collapse_duplicates, jpeg_bytes, list_images
from cv.prompts import label_prompt
from cv.schema import ImageLabel, Inventory, InventoryImage, ParsedChecklist
from cv.vertex import client as vertex_client
from cv.vertex import generate_structured

DEFAULT_WORKERS = int(os.environ.get("CV_CONCURRENCY", "6"))


def _label_one(
    c,
    path: Path,
    checklist: ParsedChecklist,
    manifest_text: str | None,
) -> InventoryImage:
    known = {r.id for r in checklist.requirements}
    jpeg = jpeg_bytes(path)
    label = generate_structured(
        c,
        jpeg=jpeg,
        prompt=label_prompt(checklist.requirements, manifest_text),
        schema=ImageLabel,
    )
    hits = [h for h in label.hits if h.id in known]
    return InventoryImage(
        file=path.name,
        hits=hits,
        note=label.note.strip(),
        findings=label.findings,
    )


def build_inventory(
    *,
    images: Path,
    requirements: Path,
    manifest: Path | None = None,
    workers: int = DEFAULT_WORKERS,
) -> Inventory:
    checklist = load_checklist(requirements)
    if spans_complete(checklist):
        manifest_text = None
    else:
        if manifest is None:
            raise ValueError("checklist missing ids/source_span; pass manifest=")
        manifest_text = manifest.read_text()

    files = list_images(images)
    if not files:
        raise FileNotFoundError(f"no images in {images}")
    unique, pairs = collapse_duplicates(files)

    c = vertex_client()
    n = max(1, workers)
    rows: list[InventoryImage] = []
    with ThreadPoolExecutor(max_workers=n) as pool:
        futs = {
            pool.submit(_label_one, c, path, checklist, manifest_text): path
            for path in unique
        }
        for fut in as_completed(futs):
            path = futs[fut]
            row = fut.result()
            extras = [b for a, b in pairs if a == path.name]
            if extras:
                row.exact_duplicate_of = extras[0]
            rows.append(row)
    rows.sort(key=lambda r: r.file)
    return Inventory(
        checklist=checklist,
        images=rows,
        exact_duplicate_pairs=pairs,
    )
