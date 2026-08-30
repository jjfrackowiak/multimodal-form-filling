# B1 · The document model

**Branch:** `feat/docmodel` → PR into `main`
**Depends on:** B0 (merged). Nothing else.
**Needs:** no API key, no GCP, no mailbox. `python-docx >= 1.2` and Pillow.


**Read [`CONTEXT.md`](CONTEXT.md) first** — what the system does, what B0 left on disk,
the contract surface, and the fixture. This brief assumes it.

---

## What you are building

`packages/mff-docmodel` — every conversion between Word documents and our types, in both
directions, for both modes. No AI, no network, no mutation of a client's document.

```python
def parse_docx(data: bytes) -> list[Node]: ...
def compile_derivative(artifact: DerivativeArtifact, source: bytes) -> tuple[bytes, RenderMap]: ...
def compile_netnew(artifact: NetNewArtifact) -> tuple[bytes, RenderMap]: ...
def attach_comments(data: bytes, comments: list[ReviewComment],
                    render_map: RenderMap, *, author: str) -> tuple[bytes, int, list[str]]: ...
```

`attach_comments` returns the document, the number attached, and the requirement ids that
fell back to a document-level anchor.

## Requirements you own

Reqs 10 (Word output carrying comments), 14, 15.

## Directories you own

```
packages/mff-docmodel/**
```

## Pin `python-docx >= 1.2` and do not plan around `Run.add_comment`

**Verified, not assumed.** 1.1.0 has *no* comment support at all — no
`Document.add_comment`, no `Document.comments`, no `Run.add_comment`. 1.2.0 provides:

```python
comment = document.add_comment(runs=[...], text="...", author="...", initials="...")
document.comments          # iterable, NOT subscriptable — use list(doc.comments)
comment.comment_id         # not .id
comment.text / .author / .initials / .timestamp
```

**`Run.add_comment` does not exist.** It appears in the project's design notes as a
proposal and was never shipped. Only `Document.add_comment(runs=...)` is real.

## The hard part: `RenderMap`

`add_comment` needs **runs**. We hold ids. `RenderMap.anchor_to_span` bridges them, and
building it is this branch's real work.

```python
class RunSpan(BaseModel):
    paragraph_index: int
    run_start: int
    run_end: int          # inclusive
```

- **Derivative:** the source document is never modified, so build the map while walking it.
  A `Node.id` must resolve to the same span every time the same bytes are parsed.
- **Net-new:** build the map *as the compiler emits each entry* — you know exactly where it
  landed, so this direction is the easy one.

**The case the fixture already proves:** in `report_reviewed.docx`, R-05/R-06 share one
section heading and R-08/R-09 share another. Two comments on one span is normal and must
work.

**The fallback:** a `ReviewComment` whose `anchor.kind == "document"` has no span — that is
`unverified`'s legitimate home. Attach it somewhere sensible (a summary section at the end
is fine) and return its requirement id in the `unanchored` list so
`CompiledForm.unanchored` is populated. Never drop it.

## Node ids must be stable across reloads

The same `.docx` bytes parsed twice must produce identical ids. Positional derivation
(`p12`, `t3.r2.c1.p0`) is acceptable **here and only here**, precisely because the
derivative document is immutable — nothing inserts, so nothing shifts. Do not carry that
assumption anywhere near net-new, where `Entry.id` is minted and never positional.

`Node.image_sha256` links an embedded image to its `JobImage`, so extract embedded media
and hash it while parsing.

## The assertion that makes derivative's promise real

**A derivative compile must leave the body byte-identical to the input, with only comments
added.** Test it: hash `word/document.xml` with the comment ranges stripped, before and
after. If that test does not exist, "derivative never mutates the client's document" is a
claim rather than a guarantee.

## Definition of done

1. `make check` green, coverage ≥ 85% on `mff_docmodel`.
2. Round-trip: `parse_docx` on `fixtures/fleet-vehicle-return/input/derivative/form_supplied.docx`
   (17 embedded images, 9 headings, 1 table) → ids stable across two parses → compile →
   opens in Word.
3. **Byte-identical-body assertion** for derivative, as above.
4. Two comments anchored to one span, exercising the R-05/R-06 shape.
5. A `document`-anchored comment lands somewhere and is reported in `unanchored`.
6. Embedded images survive the round trip and their `image_sha256` matches the file in
   `fixtures/fleet-vehicle-return/images/`.
7. Table cells get ids — the fixture's vehicle table has five rows.

## Out of scope

Deciding *which* comments to write (B6/B7), applying `DraftOp`s (B14), storage (B12),
anything async, anything that touches a model.
