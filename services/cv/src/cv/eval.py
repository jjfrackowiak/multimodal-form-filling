"""Score inventory against golden review.yaml (file ↔ requirement assignment)."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import yaml


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _pairs(doc: dict) -> set[frozenset[str]]:
    return {frozenset(p) for p in doc.get("exact_duplicate_pairs") or []}


def _ids(row: dict) -> set[str]:
    if row.get("requirement_ids"):
        return set(row["requirement_ids"])
    return {h["id"] for h in row.get("hits") or [] if h.get("id")}


def _constraint_ok(row: dict, rid: str) -> bool | None:
    for h in row.get("hits") or []:
        if h.get("id") == rid and "constraint_ok" in h:
            return h.get("constraint_ok")
    obs = row.get("observations") or {}
    if "constraint_ok" in obs:
        return obs.get("constraint_ok")
    return None


def assignment_from_review(review: dict) -> dict[str, dict]:
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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("predicted", type=Path)
    p.add_argument("--review", type=Path)
    p.add_argument("--pairs", type=Path)
    args = p.parse_args(argv)
    if not args.review and not args.pairs:
        print("need --review and/or --pairs", file=sys.stderr)
        return 2

    pred = _load(args.predicted)
    p_rows = {row["file"]: row for row in pred.get("images") or []}
    violations: list[str] = []
    checks = 0

    def check(ok: bool, msg: str) -> None:
        nonlocal checks
        checks += 1
        if not ok:
            violations.append(msg)

    if args.review:
        for name, gold in assignment_from_review(_load(args.review)).items():
            prow = p_rows.get(name)
            check(prow is not None, f"missing file {name}")
            if not prow:
                continue
            got = _ids(prow)
            check(
                gold["ids"] <= got,
                f"{name} missing ids {sorted(gold['ids'] - got)} (got {sorted(got)})",
            )
            for rid, expected_ok in gold["ok"].items():
                got_ok = _constraint_ok(prow, rid)
                if expected_ok is False:
                    check(
                        got_ok is False,
                        f"{name} {rid} should fail constraint, constraint_ok={got_ok!r}",
                    )
                elif expected_ok is True and rid in got:
                    check(
                        got_ok is not False,
                        f"{name} {rid} should satisfy constraint, constraint_ok={got_ok!r}",
                    )

    if args.pairs:
        check(
            _pairs(pred) == _pairs(_load(args.pairs)),
            "duplicate pairs mismatch",
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
    raise SystemExit(main())
