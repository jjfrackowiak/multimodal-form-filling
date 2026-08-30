# B7 · Net-new composition flow

**Branch:** `feat/flow-netnew` → PR into `main`
**Depends on:** B0 (merged), B8 (merged), B14 (`mff-applier`, merged), B15 (`mff-fakes`, merged).
**Needs:** nothing beyond `FakeLlm`. All tests run offline.


**Read [`CONTEXT.md`](CONTEXT.md) first** — what the system does, what B0 left on disk,
the contract surface, and the fixture. This brief assumes it.

---

## What you are building

`services/editor-service/src/**/flows/netnew.py` and its instruction — the agent that
**composes** a document from scratch when no form was supplied, reviewing the client's
inputs (text files, photos) against the requirements and building sections via `DraftOp`s.

Net-new mode is the creative mode. The agent builds a `FormDraft` (sections, entries) by
emitting `DraftOp`s through mutation tools, then reviews each requirement's coverage and
emits `ReviewComment`s with verdicts `realised` (met) or `shortfall` (not met).

```python
async def compose_netnew(
    req: SliceRequest,
    artifact: NetNewArtifact,
    inventory: list[ImageAnalysis],
    client_texts: dict[str, str],
    *,
    model: BaseLlm | None = None,
) -> SliceReport:
```

This function builds the agent with mutation tools, assembles `EditorDeps`, and calls
`run_slice` from B8. **You do not write a retry loop** — B8 owns that.

## Requirements you own

Reqs 1–10 for net-new mode, req 16 (verdict accuracy), req 17 (retry correctness).

## Directories you own

```
services/editor-service/src/**/flows/netnew.py
services/editor-service/src/**/flows/tools.py
services/editor-service/tests/flows/netnew/
```

`llm/` is B8's. `flows/derivative.py` is B6's.

## Mutation tools

The agent needs tools to build the document. These are ADK tools — plain functions that
`build_agent` registers on the `LlmAgent`. Each closes over `EditorDeps` so it can mutate
`artifact.draft` in place and append a `DraftOp` to `deps.op_log`.

```python
def make_tools(deps: EditorDeps) -> list[Callable]:
    draft = deps.artifact.draft  # type: ignore[union-attr]

    def set_field(section_id: str, entry_id: str, value: str) -> str:
        """Set or overwrite a field in the draft."""
        ...
        deps.op_log.append(DraftOp(kind="set", ...))
        return "ok"

    def append_entry(section_id: str, label: str, value: str) -> str:
        """Add a new entry to a section."""
        ...
        deps.op_log.append(DraftOp(kind="append", ...))
        return "ok"

    def delete_entry(section_id: str, entry_id: str) -> str:
        """Remove an entry from a section."""
        ...
        deps.op_log.append(DraftOp(kind="delete", ...))
        return "ok"

    return [set_field, append_entry, delete_entry]
```

**The tool return value is a string** — ADK tool returns must be serialisable to a
`types.Part`, so return `"ok"` or an error message. ADK passes `tool_context: ToolContext`
if the parameter is declared; you may need it for logging but not for mutation.

## The instruction

The agent's `instruction` string must:

1. Explain the verdict vocabulary: `realised` (requirement met), `shortfall` (not met).
2. Explain that the agent **builds the document** by calling tools (`set_field`,
   `append_entry`, `delete_entry`) before reviewing.
3. Say that the scaffold has sections matching the requirement categories, and entries
   should be created within the appropriate section.
4. Explain the inventory and client texts — they are context for populating the document
   and deciding verdicts, just like in derivative mode.
5. Say that `anchor` must point to the section or entry the requirement governs.
6. Same rules as derivative for justification (specific, naming photos) and suggestion
   (required on shortfall, forbidden on realised).

## The scaffold

A `NetNewArtifact` starts with a `FormDraft` that has sections matching the headings in
`structure.yaml`. The agent populates entries within those sections. `compose_netnew`
creates this scaffold before running the agent.

## What to test against

Same fixtures as B6 — the verdicts are the same (R-01 shortfall, R-04 shortfall, 8 others
realised), just with different vocabulary and DraftOps.

## Definition of done

1. `make check` green, coverage ≥ 85%.
2. **Every test uses `FakeLlm` from `mff-fakes`. No network in CI.**
3. R-04 verdict is `shortfall` — same headline case as B6.
4. R-01 verdict is `shortfall` — same count case.
5. All 8 passing requirements produce `realised` verdicts.
6. `DraftOp`s are present in the report — net-new builds the document.
7. Mutation tools tested directly: `set_field` mutates the draft, `append_entry` adds an
   entry, `delete_entry` removes one. Each appends to `op_log`.
8. Anchors resolve: every comment's `anchor.target_id` exists in the artifact's draft
   entries or sections.
9. Instruction string is at least 200 characters.
10. The tools produce valid `DraftOp`s that `mff-applier` can consume — build a small
    draft, run the tools, pass the ops to `apply_slice` from `mff-applier` and assert
    no error.

## Out of scope

Derivative review (B6), the retry loop (B8), document compilation (B1), orchestration (B5),
delivery (B13).
