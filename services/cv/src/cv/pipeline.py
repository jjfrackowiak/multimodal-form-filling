"""Editor-facing tool: checklist + photo paths → inventory."""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from cv.checklist import spans_complete
from cv.images import collapse_duplicates, jpeg_bytes
from cv.prompts import label_prompt
from cv.schema import ImageLabel, Inventory, InventoryImage, ParsedChecklist
from cv.vertex import client as vertex_client
from cv.vertex import generate_structured

log = logging.getLogger("cv")


def _worker_limit() -> int:
    # 3 parallel generateContent calls still 429 on this project's Vertex quota.
    return max(1, int(os.environ.get("CV_MAX_WORKERS", "1")))


def _label_one(
    c,
    path: Path,
    checklist: ParsedChecklist,
    manifest_text: str | None,
    uri: str | None,
) -> InventoryImage:
    known = {r.id for r in checklist.requirements}
    label = generate_structured(
        c,
        jpeg=jpeg_bytes(path),
        prompt=label_prompt(checklist.requirements, manifest_text),
        schema=ImageLabel,
    )
    hits = [h for h in label.hits if h.id in known]
    return InventoryImage(
        file=path.name,
        uri=uri,
        hits=hits,
        note=label.note.strip(),
        findings=label.findings,
    )


def build_inventory(
    image_paths: list[Path],
    checklist: ParsedChecklist,
    *,
    manifest_text: str | None = None,
    workers: int | None = None,
    source_uris: dict[str, str] | None = None,
) -> Inventory:
    if not spans_complete(checklist) and not (manifest_text or "").strip():
        raise ValueError("checklist missing ids/text; pass manifest_text")
    if spans_complete(checklist):
        manifest_text = None
    if not image_paths:
        raise FileNotFoundError("no images")

    unique, pairs = collapse_duplicates(image_paths)
    limit = _worker_limit()
    cap = limit if workers is None else max(1, min(workers, limit))
    n = max(1, min(len(unique), cap))
    log.info("labeling %d images with %d workers (cap %s)", len(unique), n, limit)

    uris = source_uris or {}
    c = vertex_client()
    rows: list[InventoryImage] = []
    with ThreadPoolExecutor(max_workers=n) as pool:
        futs = {
            pool.submit(
                _label_one,
                c,
                path,
                checklist,
                manifest_text,
                uris.get(path.name),
            ): path
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
