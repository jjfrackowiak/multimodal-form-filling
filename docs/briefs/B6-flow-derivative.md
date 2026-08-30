# B6 · Derivative review flow

**Branch:** `feat/flow-derivative` → PR into `main`
**Depends on:** B0 (merged), B8 (merged), B15 (`mff-fakes`, merged).
**Needs:** nothing beyond `FakeLlm`. All tests run offline.


**Read [`CONTEXT.md`](CONTEXT.md) first** — what the system does, what B0 left on disk,
the contract surface, and the fixture. This brief assumes it.

---

## What you are building

`services/editor-service/src/**/flows/derivative.py` and its instruction — the agent that
**reviews** a client-supplied Word form against parsed requirements and image inventory.

Derivative mode never mutates the client's document body. It reads the `DerivativeArtifact`
(a list of `Node`s, already parsed from the .docx by B1), compares each requirement against
the photo inventory and the document structure, and emits `ReviewComment`s. No `DraftOp`s.

```python
async def review_derivative(
    req: SliceRequest,
    artifact: DerivativeArtifact,
    inventory: list[ImageAnalysis],
    *,
    model: BaseLlm | None = None,
) -> SliceReport:
```

This function builds the agent (via `build_agent` from B8), assembles `EditorDeps`, and
calls `run_slice` from B8. **You do not write a retry loop** — B8 owns that.

## Requirements you own

Reqs 1–10 for derivative mode, req 16 (verdict accuracy), req 17 (retry correctness —
though the loop itself is B8's, you own the instruction that makes the model self-correct).

## Directories you own

```
services/editor-service/src/**/flows/derivative.py
services/editor-service/src/**/flows/__init__.py
services/editor-service/tests/flows/derivative/
```

`llm/` is B8's. `flows/netnew.py` is B7's.

## The instruction

The agent's `instruction` string is the review policy — the thing that tells the model
*how* to decide verdicts. It must:

1. Explain the verdict vocabulary: `pass` (requirement met), `fail` (not met).
2. Explain what `satisfied` means for a photo requirement: the right count *and* any
   constraint met. Count alone is not enough — R-04 has the right count but fails the
   positional constraint.
3. Say that `justification` must name specific photos and explain *why* they satisfy or
   fail, not just assert that they do.
4. Say that `suggestion` is required on `fail` and forbidden on `pass`.
5. Say that `anchor` must point to the section the requirement governs — `kind="section"`,
   `target_id` = the node id of the heading. Never `kind="document"` unless there is no
   matching section.
6. Explain the inventory: a list of `ImageAnalysis` objects, each naming a photo and the
   requirement ids it covers, with `constraint_ok` and `constraint_evidence` when relevant.
   The model does not re-analyse photos — it reads the inventory.

## The vision tool

The vision inventory is **pre-built at ingest** and passed in as `list[ImageAnalysis]`.
There is no tool call to a vision service during the review — the inventory is data, not
a function. Inject it into the instruction context as structured text so the model can
reference specific images by filename.

## What to test against

- **`fixtures/fleet-vehicle-return/expected_requirements.yaml`** — the 10 requirements.
- **`fixtures/fleet-vehicle-return/inventory.yaml`** — the photo inventory.
- **`fixtures/fleet-vehicle-return/expected_output/review.yaml`** — the golden verdicts,
  including R-01 fail (count short) and R-04 fail (constraint).
- **`fixtures/fleet-vehicle-return/expected_output/structure.yaml`** — the structural eval.

Build a `DerivativeArtifact` with `Node`s matching `form_supplied.docx`'s section structure
(9 sections from the structure.yaml headings). The model doesn't see the .docx — it sees
`Node`s and the inventory.

## Definition of done

1. `make check` green, coverage ≥ 85%.
2. **Every test uses `FakeLlm` from `mff-fakes`. No network in CI.**
3. R-04 verdict is `fail` — the headline case. Script `FakeLlm` to return a comment where
   `1000040420.jpg` satisfies the constraint but `IMG_20260830_132755 (5).jpg` does not.
   The test asserts the verdict, not just that the run completes.
4. R-01 verdict is `fail` — count short (2 required, 1 supplied).
5. All 8 passing requirements produce `pass` verdicts with non-empty justifications.
6. No `DraftOp`s in the report — derivative never mutates.
7. Anchors resolve: every comment's `anchor.target_id` exists in the artifact's `Node` ids.
8. Instruction string is at least 200 characters — this is not a one-liner.
9. The golden review from `review.yaml` is reproducible: script `FakeLlm` with the golden
   comments, run `review_derivative`, and assert the `SliceReport` matches structurally
   (ids, verdicts, non-empty justifications, anchors resolve).
10. A mutation test: flip R-04 from fail to pass in the scripted output. Assert the
    structural eval (or your own assertion) catches it.

## Out of scope

Net-new composition (B7), the retry loop (B8), document parsing (B1), orchestration (B5),
delivery (B13).
