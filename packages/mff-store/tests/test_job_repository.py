"""JobRepository — D2: job status must be answerable at all, from any adapter."""

from __future__ import annotations

from factories import make_job_record


async def test_put_then_get_round_trips(job_repo: object) -> None:
    record = make_job_record("job-1", "req-1")
    await job_repo.put(record)  # type: ignore[attr-defined]

    loaded = await job_repo.get("job-1")  # type: ignore[attr-defined]
    assert loaded is not None
    assert loaded.job_id == "job-1"
    assert loaded.request_id == "req-1"
    assert loaded.status == "running"


async def test_get_missing_returns_none(job_repo: object) -> None:
    assert await job_repo.get("no-such-job") is None  # type: ignore[attr-defined]


async def test_put_is_an_upsert(job_repo: object) -> None:
    await job_repo.put(make_job_record("job-1", "req-1", status="running"))  # type: ignore[attr-defined]
    await job_repo.put(make_job_record("job-1", "req-1", status="done"))  # type: ignore[attr-defined]

    loaded = await job_repo.get("job-1")  # type: ignore[attr-defined]
    assert loaded is not None
    assert loaded.status == "done"


async def test_for_request_is_the_barrier(job_repo: object) -> None:
    """`for_request` is what tells the orchestrator all of a request's jobs have
    settled — it must return every job for a request and nothing from another."""
    await job_repo.put(make_job_record("job-1", "req-1"))  # type: ignore[attr-defined]
    await job_repo.put(make_job_record("job-2", "req-1"))  # type: ignore[attr-defined]
    await job_repo.put(make_job_record("job-3", "req-2"))  # type: ignore[attr-defined]

    jobs = await job_repo.for_request("req-1")  # type: ignore[attr-defined]
    assert {j.job_id for j in jobs} == {"job-1", "job-2"}


async def test_for_request_with_no_jobs_returns_empty(job_repo: object) -> None:
    assert await job_repo.for_request("no-such-request") == []  # type: ignore[attr-defined]
