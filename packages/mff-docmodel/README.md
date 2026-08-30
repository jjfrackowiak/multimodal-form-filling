# mff-docmodel

Every conversion between Word documents and our types, in both directions, for both
modes. No AI, no network, no mutation of a client's document.

```python
def parse_docx(data: bytes) -> list[Node]: ...
def compile_derivative(artifact: DerivativeArtifact, source: bytes) -> tuple[bytes, RenderMap]: ...
def compile_netnew(artifact: NetNewArtifact) -> tuple[bytes, RenderMap]: ...
def attach_comments(data: bytes, comments: list[ReviewComment],
                    render_map: RenderMap, *, author: str) -> tuple[bytes, int, list[str]]: ...
```

## `python-docx` >= 1.2, verified

1.1.0 ships no comment support at all — no `Document.add_comment`, no `Document.comments`.
**`Run.add_comment` does not exist in any released version**; it is a proposal in the
project's own design notes that was never shipped. The only real entry point is
`Document.add_comment(runs=...)`, which takes a `Run` or a sequence of `Run`s (only the
first and last are used) and returns a `Comment` with `.comment_id` (not `.id`).
`document.comments` is iterable but **not subscriptable** — `list(doc.comments)` first.

## `RenderMap` — the bridge, and what it cannot address

`add_comment` needs runs; the rest of the system holds ids. `RenderMap.anchor_to_span`
maps a `Node.id` or `Entry.id` to a `RunSpan(paragraph_index, run_start, run_end)`, where
`paragraph_index` indexes `Document.paragraphs` — python-docx's **top-level** paragraph
list, built from `CT_Body.p_lst` (direct `<w:p>` children of the body only).

That has one real consequence: **a table cell can never be a `RunSpan` target.** A cell's
paragraphs live under `<w:tbl>/<w:tr>/<w:tc>`, not as direct body children, so they are
invisible to `Document.paragraphs` and there is no way to name one with this shape of
`RunSpan`. Table cells still get stable `Node.id`s (`t{table}.r{row}.c{col}`) for identity,
but they are deliberately absent from `anchor_to_span` — a comment anchored to one falls
back to the document-level anchor in `attach_comments`, the same as an `unverified`
verdict. If a future requirement needs to comment on a table cell directly, `RunSpan`
itself needs a new shape; that is outside this branch's scope to decide.

Two ids can map to the same span — the fixture's real shape (R-05/R-06 on "5. Przednia
szyba", R-08/R-09 on "7. Bagażnik i wyposażenie", both sections' headings). Nothing special
is required: `Document.add_comment` is simply called twice against the same run pair, and
python-docx nests the resulting `commentRangeStart`/`commentRangeEnd` pairs correctly
(verified byte-for-byte against `expected_output/report_reviewed.docx`).

## Derivative ids are positional, and that is a scoped exception

`Node.id` is derived from position (`p12` for a body paragraph, `p12.i1` for the second
image in a multi-image paragraph, `t0.r2.c1` for a table cell) rather than minted, because
a derivative document never changes shape between one parse and the next — nothing
inserts, so nothing shifts. `compile_derivative` re-walks the exact same traversal
(`parse.walk`) rather than trusting a persisted `artifact.nodes`, so the ids it resolves
into `RenderMap` are *guaranteed*, not merely expected, to agree with a fresh `parse_docx`
of the same bytes. This positional scheme is intentionally **not** reused for net-new,
where `Entry.id` is minted once and never repositioned.

## The byte-identical-body promise

`compile_derivative` returns `source` untouched; only `attach_comments` writes anything,
and only comment markup (`commentRangeStart`/`commentRangeEnd`/`commentReference` — never
a change to a `<w:t>`, a run, or a paragraph). Verified by hashing `word/document.xml` with
the comment elements stripped back out, before and after
(`tests/test_byte_identical.py`), including three mutation tests that deliberately corrupt
the body first to prove the comparison can actually fail.

## What DoD 6 could not be verified as literally stated

The brief's DoD asks that an embedded image's `image_sha256` "matches the file in
`fixtures/fleet-vehicle-return/input/netnew/WN-7020U/`". It does not, byte-for-byte: the
15 distinct photographs embedded in `form_supplied.docx` were resized when embedded
(e.g. 1400×1050 vs. the loose files' 1536×2048/2048×1536), so their sha256 differs from
the loose `.jpg` files' sha256 even though they are the same underlying photographs. This
is true of the fixture as shipped, not a bug in this package — `image_sha256` here is
computed from the bytes exactly as extracted from the `.docx` (the only correct reading of
`BlobRef`'s "content-addressed pointer to bytes"), and that hash is stable across repeated
parses of the same document, which is the guarantee this branch actually owns. What *does*
line up: both artifacts independently reduce to 15 distinct images out of 17 delivered
files (`test_image_sha256_matches_extraction`), matching `review.yaml`'s
`distinct_images: 15`.

## Net-new images are referenced, not embedded

`compile_netnew(artifact: NetNewArtifact) -> tuple[bytes, RenderMap]` never receives blob
bytes — only `BlobRef`s (uri + hash + size). This package has no network access and, by
the workspace's own import-linter layering, cannot import `mff_store` (siblings in the
same layer). An `Entry`'s images are therefore surfaced as a short text reference
(`[zdjęcie: <sha256 prefix>]`) next to its value rather than as an embedded picture.
Whichever branch owns delivery/applying should decide if and how a real picture gets
embedded — nothing here silently drops the reference, but nothing here can resolve it to
pixels either.

## The "caption" kind is a heuristic, not a style

The fixture's photo captions ("Komora silnika", "Fotel kierowcy", …) use the same `Normal`
paragraph style as everything else — there is no distinct Word style to key off. A
paragraph is classified `kind="caption"` when it immediately follows an image-bearing
paragraph and carries text; otherwise it is `"heading"` (style name starts with
`"Heading"`) or plain `"paragraph"`. This is a judgment call this branch made, not
something asserted by the contract or the DoD — worth a second look if a later branch
needs to distinguish captions more precisely.
