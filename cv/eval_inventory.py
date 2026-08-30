#!/usr/bin/env python3
"""Score a generated inventory.yaml against the golden fixture labels.

    python cv/eval_inventory.py path/to/generated.yaml \\
        fixtures/fleet-vehicle-return/inventory.yaml

Exit 0 only if depicts (and headliner shot_from) match for every golden file
and duplicate pairs match as unordered pairs. Notes are not scored.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def by_file(doc: dict) -> dict[str, dict]:
    return {row["file"]: row for row in doc.get("images") or []}


def pair_set(doc: dict) -> set[frozenset[str]]:
    return {frozenset(p) for p in doc.get("exact_duplicate_pairs") or []}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("predicted", type=Path)
    parser.add_argument("golden", type=Path)
    args = parser.parse_args()

    pred = load(args.predicted)
    gold = load(args.golden)
    g_rows = by_file(gold)
    p_rows = by_file(pred)

    violations: list[str] = []
    checks = 0

    def check(ok: bool, msg: str) -> None:
        nonlocal checks
        checks += 1
        if not ok:
            violations.append(msg)

    for name, grow in g_rows.items():
        prow = p_rows.get(name)
        check(prow is not None, f"missing file {name}")
        if not prow:
            continue
        check(
            prow.get("depicts") == grow.get("depicts"),
            f"{name} depicts {prow.get('depicts')!r} != {grow.get('depicts')!r}",
        )
        if grow.get("depicts") == "headliner" or prow.get("depicts") == "headliner":
            check(
                prow.get("shot_from") == grow.get("shot_from"),
                f"{name} shot_from {prow.get('shot_from')!r} != {grow.get('shot_from')!r}",
            )

    extra = sorted(set(p_rows) - set(g_rows))
    # Duplicate extras are allowed only in exact_duplicate_pairs, not as extra image rows.
    check(not extra, f"unexpected image rows: {extra}")

    check(pair_set(pred) == pair_set(gold), f"duplicate pairs {pair_set(pred)} != {pair_set(gold)}")

    passed = checks - len(violations)
    if violations:
        print(f"FAIL  {passed}/{checks} checks passed")
        for v in violations:
            print(f"  - {v}")
        return 1
    print(f"PASS  {passed}/{checks} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
