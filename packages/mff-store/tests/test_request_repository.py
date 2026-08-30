"""RequestRepository — req 12: state outlives any run."""

from __future__ import annotations

from factories import make_request_record


async def test_put_then_get_round_trips(request_repo: object) -> None:
    record = make_request_record("req-1")
    await request_repo.put(record)  # type: ignore[attr-defined]

    loaded = await request_repo.get("req-1")  # type: ignore[attr-defined]
    assert loaded is not None
    assert loaded.request_id == "req-1"
    assert loaded.manifest_raw == record.manifest_raw
    assert loaded.job_ids == ["job-1"]


async def test_get_missing_returns_none(request_repo: object) -> None:
    assert await request_repo.get("no-such-request") is None  # type: ignore[attr-defined]


async def test_manifest_survives_non_ascii_bytes(request_repo: object) -> None:
    """The manifest is real, client-written Polish text — never normalise it, and never
    let it come back mangled through the store."""
    record = make_request_record("req-polish")
    await request_repo.put(record)  # type: ignore[attr-defined]

    loaded = await request_repo.get("req-polish")  # type: ignore[attr-defined]
    assert loaded is not None
    assert "zdjęć" in loaded.manifest_raw
    assert "maską" in loaded.manifest_raw
