#!/usr/bin/env python3
"""Score generated inventory against golden fixture data.

Manifest-driven output (requirement_ids) is scored against review.yaml
(file ↔ requirement assignment). Legacy depicts YAML still works if present.

    python cv/eval_inventory.py cv/inventory.generated.yaml \\
        --review fixtures/fleet-vehicle-return/expected_output/review.yaml \\
        --pairs fixtures/fleet-vehicle-return/inventory.yaml
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import yaml


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def pair_set(doc: dict) -> set[frozenset[str]]:
    return {frozenset(p) for p in doc.get("exact_duplicate_pairs") or []}


def assignment_from_review(review: dict) -> dict[str, dict]:
    """file -> {ids: set[str], constraint_ok: bool|None} from golden verdicts."""
    by_file: dict[str, dict] = defaultdict(lambda: {"ids": set(), "ok": {}})
    for row in review.get("verdicts") or []:
        rid = row["requirement_id"]
        for name in row.get("satisfied_by") or []:
            by_file[name]["ids"].add(rid)
            by_file[name]["ok"][rid] = True
        for name in row.get("rejected") or []:
            by_file[name]["ids"].add(rid)
            by_file[name]["ok"][rid] = False
    return by_file


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("predicted", type=Path)
    parser.add_argument("--golden", type=Path, help="legacy depicts inventory.yaml")
    parser.add_argument("--review", type=Path, help="golden review.yaml for requirement_ids")
    parser.add_argument("--pairs", type=Path, help="inventory.yaml used only for duplicate pairs")
    args = parser.parse_args()
    if not args.golden and not args.review:
        print("need --golden and/or --review", file=sys.stderr)
        return 2

    pred = load(args.predicted)
    p_rows = {row["file"]: row for row in pred.get("images") or []}
    violations: list[str] = []
    checks = 0

    def check(ok: bool, msg: str) -> None:
        nonlocal checks
        checks += 1
        if not ok:
            violations.append(msg)

    if args.review:
        gold_asg = assignment_from_review(load(args.review))
        for name, gold in gold_asg.items():
            prow = p_rows.get(name)
            check(prow is not None, f"missing file {name}")
            if not prow:
                continue
            got = set(prow.get("requirement_ids") or [])
            check(gold["ids"] <= got, f"{name} missing ids {sorted(gold['ids'] - got)} (got {sorted(got)})")
            pred_ok = (prow.get("observations") or {}).get("constraint_ok")
            for rid, expected_ok in gold["ok"].items():
                if expected_ok is False:
                    check(
                        pred_ok is False,
                        f"{name} {rid} should fail constraint, constraint_ok={pred_ok!r}",
                    )
                elif expected_ok is True and rid in got:
                    # Pass photos of constrained reqs should be true or null
                    check(
                        pred_ok is not False,
                        f"{name} {rid} should satisfy constraint, constraint_ok={pred_ok!r}",
                    )

    if args.golden:
        gold = load(args.golden)
        g_rows = {row["file"]: row for row in gold.get("images") or []}
        for name, grow in g_rows.items():
            if "depicts" not in grow:
                continue
            prow = p_rows.get(name)
            if not prow or "depicts" not in prow:
                continue
            check(
                prow.get("depicts") == grow.get("depicts"),
                f"{name} depicts {prow.get('depicts')!r} != {grow.get('depicts')!r}",
            )

    pair_src = args.pairs or args.golden
    if pair_src:
        check(
            pair_set(pred) == pair_set(load(pair_src)),
            f"duplicate pairs {pair_set(pred)} != {pair_set(load(pair_src))}",
        )

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
