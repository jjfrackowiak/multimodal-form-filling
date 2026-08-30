"""Stage 1: the deterministic pre-split."""

from __future__ import annotations

from mff_manifest import presplit

from golden import RAW


def test_every_chunk_is_a_verbatim_substring_at_its_own_offset() -> None:
    for chunk in presplit(RAW):
        assert RAW[chunk.offset : chunk.offset + len(chunk.text)] == chunk.text


def test_fleet_manifest_has_no_blank_lines_so_it_is_one_chunk() -> None:
    # The whole document goes to the extractor in one call — the cross-line link between
    # line 4 and line 10 depends on it seeing both at once.
    chunks = presplit(RAW)
    assert len(chunks) == 1
    assert chunks[0].text == RAW
    assert chunks[0].offset == 0


def test_splits_on_blank_lines_and_drops_whitespace_only_pieces() -> None:
    raw = "first paragraph\nstill first\n\n\nsecond paragraph\n"
    chunks = presplit(raw)
    assert [c.text.strip() for c in chunks] == ["first paragraph\nstill first", "second paragraph"]
    for chunk in chunks:
        assert raw[chunk.offset : chunk.offset + len(chunk.text)] == chunk.text


def test_empty_manifest_yields_one_empty_chunk_not_zero() -> None:
    # A splitter that returns no chunks for empty input would let parse_manifest skip the
    # model call entirely and call that "success" — this asserts against that shortcut.
    chunks = presplit("")
    assert len(chunks) == 1
    assert chunks[0].text == ""
    assert chunks[0].offset == 0


def test_whitespace_only_manifest_yields_one_chunk() -> None:
    chunks = presplit("   \n  \n\n   ")
    assert len(chunks) == 1
