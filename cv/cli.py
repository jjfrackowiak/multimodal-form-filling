"""CLI for the CV tool. Editor code should call cv.build_inventory instead."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cv.checklist import load_checklist, spans_complete
from cv.dump import inventory_to_yaml
from cv.images import list_images
from cv.pipeline import MAX_WORKERS, build_inventory
from cv.vertex import LOCATION, MODEL, PROJECT


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("images", type=Path)
    p.add_argument("--requirements", type=Path, required=True)
    p.add_argument("--manifest", type=Path, default=None)
    p.add_argument("--out", type=Path, default=Path("inventory.generated.yaml"))
    p.add_argument(
        "--workers",
        type=int,
        default=None,
        help=f"parallel Vertex calls; default min(n_images, {MAX_WORKERS})",
    )
    args = p.parse_args(argv)

    print(
        f"Vertex project={PROJECT} location={LOCATION} model={MODEL}",
        flush=True,
    )
    checklist = load_checklist(args.requirements)
    manifest_text = None
    if not spans_complete(checklist):
        if not args.manifest:
            print("checklist missing ids/source_span; pass --manifest", file=sys.stderr)
            return 2
        manifest_text = args.manifest.read_text()
    try:
        inv = build_inventory(
            list_images(args.images.resolve()),
            checklist,
            manifest_text=manifest_text,
            workers=args.workers,
        )
    except (ValueError, FileNotFoundError) as e:
        print(e, file=sys.stderr)
        return 2

    args.out.write_text(inventory_to_yaml(inv))
    print(
        f"wrote {args.out} ({len(inv.images)} unique / "
        f"{len(inv.exact_duplicate_pairs)} dupe pairs)",
        flush=True,
    )
    return 0
