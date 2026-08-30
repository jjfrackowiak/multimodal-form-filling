"""BlobStore — content-addressing, and the reason documents don't live in Firestore.

`fixtures/fleet-vehicle-return/input/netnew/WN-7020U/*.jpg` is 17 files, 15 distinct —
the content-addressing test runs against real duplicates rather than synthetic ones.
`expected_output/report_reviewed.docx` is 2.8 MB, which is why it goes to GCS rather than
Firestore, where it would breach the 1 MiB document cap.
"""

from __future__ import annotations

import pytest
from factories import FIXTURE_DIR

from mff_store.errors import BlobNotFoundError

NETNEW_IMAGES_DIR = FIXTURE_DIR / "input" / "netnew" / "WN-7020U"
REVIEWED_DOCX = FIXTURE_DIR / "expected_output" / "report_reviewed.docx"


async def test_put_then_get_round_trips(blob_store: object) -> None:
    data = b"some bytes"
    ref = await blob_store.put(data, content_type="text/plain", kind="text")  # type: ignore[attr-defined]

    fetched = await blob_store.get(ref)  # type: ignore[attr-defined]
    assert fetched == data
    assert ref.size_bytes == len(data)


async def test_get_missing_raises(blob_store: object) -> None:
    data = b"never stored"
    ref = await blob_store.put(data, content_type="text/plain", kind="text")  # type: ignore[attr-defined]
    # Same shape, different (unregistered) URI — proves get() checks existence rather
    # than always succeeding.
    forged = ref.model_copy(update={"uri": ref.uri + "-does-not-exist"})

    with pytest.raises(BlobNotFoundError):
        await blob_store.get(forged)  # type: ignore[attr-defined]


async def test_identical_bytes_dedupe(blob_store: object) -> None:
    data = b"the same photo, twice"
    ref_a = await blob_store.put(data, content_type="image/jpeg", kind="image")  # type: ignore[attr-defined]
    ref_b = await blob_store.put(data, content_type="image/jpeg", kind="image")  # type: ignore[attr-defined]

    assert ref_a.uri == ref_b.uri
    assert ref_a.sha256 == ref_b.sha256


async def test_signed_url_returns_a_url(blob_store: object) -> None:
    ref = await blob_store.put(b"x", content_type="text/plain", kind="text")  # type: ignore[attr-defined]
    url = await blob_store.signed_url(ref, ttl_seconds=60)  # type: ignore[attr-defined]
    assert isinstance(url, str)
    assert url  # non-empty


async def test_fixture_images_17_files_15_distinct_blobs(blob_store: object) -> None:
    files = sorted(NETNEW_IMAGES_DIR.glob("*.jpg"))
    assert len(files) == 17, "fixture changed shape — brief asserts 17 files, 15 distinct"

    refs = []
    for path in files:
        data = path.read_bytes()
        ref = await blob_store.put(data, content_type="image/jpeg", kind="image")  # type: ignore[attr-defined]
        refs.append(ref)

    assert len({r.uri for r in refs}) == 15
    assert len({r.sha256 for r in refs}) == 15

    # And every one of the 17 reads back exactly the bytes it was given.
    for path, ref in zip(files, refs, strict=True):
        assert await blob_store.get(ref) == path.read_bytes()  # type: ignore[attr-defined]


async def test_reviewed_docx_round_trips_through_the_blob_store(blob_store: object) -> None:
    """Firestore caps a document at 1 MiB; this document is 2.8 MB, which is the entire
    reason it goes to GCS instead."""
    data = REVIEWED_DOCX.read_bytes()
    assert len(data) > 2_000_000, "fixture changed shape — expected a multi-MB .docx"

    ref = await blob_store.put(  # type: ignore[attr-defined]
        data,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        kind="document",
    )
    assert ref.size_bytes == len(data)

    fetched = await blob_store.get(ref)  # type: ignore[attr-defined]
    assert fetched == data
