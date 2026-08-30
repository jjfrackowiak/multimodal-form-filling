# B14 · The applier

**Branch:** `feat/applier` → PR into `main`
**Depends on:** B0 (merged). Nothing else.
**Needs:** no API key, no GCP, no mailbox, no network. Pure functions.


**Read [`CONTEXT.md`](CONTEXT.md) first** — what the system does, what B0 left on disk,
the contract surface, and the fixture. This brief assumes it.

---

## What you are building

`packages/mff-applier` — the one place a validated `SliceReport` becomes changes to an
`Artifact`. Pure functions over `(Artifact, SliceReport) → Artifact`. No I/O, no model, no
async.

Every mode's correctness funnels through this package, which makes it **the easiest thing
in the repo to test exhaustively and the most worth testing**. Aim for genuinely
exhaustive: this is not a module where 85% coverage is the goal.

## Requirements you own

Req 14 (surgical, no full regeneration) and req 15 (output tools apply the edits).

## Directories you own

```
packages/mff-applier/**
```

Nothing else. `mff-contracts` is frozen — if you need a change there, raise it in the PR
description rather than making it.

## The API

```python
def apply_slice(artifact: Artifact, report: SliceReport,
                scope_ids: list[str]) -> ApplyResult: ...

class ApplyResult(BaseModel):
    artifact: Artifact
    overwrites: list[Overwrite]      # the D3 signal — see below
    rejected: list[Rejection]        # ops refused, with the reason
```

`ApplyResult`, `Overwrite` and `Rejection` are **yours to define** in `mff-applier` — they
are internal to the orchestrator↔applier boundary, not wire types, so they do not belong
in the frozen contract.

## What it must enforce

**1. Derivative artifacts are never mutated.** `DerivativeArtifact` has no draft. A
`SliceReport` for a derivative slice carries `comments` and an **empty** `ops` list. If
`ops` is non-empty on a derivative artifact, that is a bug in the caller — reject the whole
report rather than silently ignoring it, and say so.

Comments are appended to `artifact.comments`. The `nodes` list and `source` blob are
returned untouched, byte-identical.

**2. Scope violations are rejected, not applied.** Every `DraftOp` must target a section or
entry within `scope_ids`. An op outside it is a `Rejection`, never applied — slice
isolation is enforced *here*, deterministically, never by asking a prompt nicely.

**3. `DraftOp` semantics.**

| `kind` | Requires | Effect |
|---|---|---|
| `append` | `section_id` | Mint a new `Entry` with a fresh id and a fractional `order` after the section's last entry. `set_by` = the op's `requirement_id`. |
| `set` | `entry_id` | Replace `value` and/or `images` on an existing entry. Its `id` and `order` do **not** change. |
| `delete` | `entry_id` | Remove the entry. See the dangling-comment rule below. |

**4. Fractional ordering.** `Entry.order` is a string compared lexicographically.
Appending between two entries must produce a key that sorts between them **without
touching any sibling**. Implement it properly (the LexoRank/Figma approach — take the
midpoint of the character range, extending the string when two keys are adjacent). An
implementation that renumbers siblings defeats the entire reason `order` is a string.

**5. Deleting an entry that a comment depends on.** A `ReviewComment` anchored to an entry
that is then deleted becomes a proof of nothing. Refuse the delete and return a
`Rejection` naming the comment. The orchestrator decides what to do; the applier does not
silently strand evidence.

**6. Overwrite detection — the D3 signal.** When a `set` or `delete` targets an entry whose
`set_by` is a **different** requirement, record an `Overwrite(entry_id, previous_requirement,
new_requirement)`. Do not block it — a later requirement legitimately supersedes an earlier
one sometimes. But it is the only mechanical signal we have that two requirements may
contradict each other, so it must be surfaced rather than swallowed.

## What to test against

`fixtures/fleet-vehicle-return/` gives you real data without inventing any:

- **`expected_output/review.yaml`** — ten real `ReviewComment`s, two of them `fail` with
  suggestions. Build `SliceReport`s from these rather than making up comments.
- **`expected_requirements.yaml`** — R-01…R-10 with their `ordinal`s, so a slice of six
  and a slice of four are easy to construct.
- The **net-new** side is `input/netnew/WN-7020U/` — 17 images and 2 `.txt` files, which is
  what a `FormDraft` gets built from. R-02 wants **four** seat entries, so it is the
  natural `append` test.

## Definition of done

1. `make check` green.
2. **Coverage 100% on `mff_applier`.** Not 85%. This module is small and pure; there is no
   excuse for an untested branch.
3. Property test on fractional ordering: for any sequence of appends and inserts, entries
   read back in the intended order and **no pre-existing entry's `order` string changed**.
4. A test that a derivative artifact round-trips with `nodes` and `source` identical
   objects, comments appended.
5. A test for each rejection reason, each `DraftOp` kind, and the overwrite signal.
6. A test that deleting a comment-anchored entry is refused with the comment named.

## Out of scope

Deciding *what* to do about overwrites or rejections (orchestrator), rendering (B1),
persistence (B12), anything async, anything that touches a model.
