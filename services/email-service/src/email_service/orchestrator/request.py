"""`run_request` — fan a request's jobs out (parallel, semaphore-bounded), sequence
each job's slices via `run_job`, and hold the delivery barrier: one `RequestResult`
once every job has settled.

`mode` is per job (see `mff_contracts.jobs`), never per request — a single request may
hold both derivative and net-new jobs, and each is dispatched through the same
`run_job` regardless, since `run_job` already reads `JobRequest.mode` for itself.

`status="partial"` means some jobs finished and others did not — never a
half-reviewed document, because `run_job` only ever produces a `document` after its
own completeness check has passed and it has compiled cleanly. A `done` job carrying
`unverified` comments is not partial: only `JobRecord.status != "done"` counts against
the barrier.
"""

from __future__ import annotations

import asyncio
from typing import Literal

from mff_contracts import JobCursor, JobRecord, JobRequest, RequestRecord, RequestResult

from .deps import OrchestratorDeps
from .job import run_job

__all__ = ["run_request"]


async def run_request(
    record: RequestRecord, jobs: list[JobRequest], deps: OrchestratorDeps
) -> RequestResult:
    semaphore = asyncio.Semaphore(deps.max_concurrent_jobs)

    async def _bounded(job: JobRequest) -> JobRecord:
        async with semaphore:
            return await run_job(job, deps)

    raw = await asyncio.gather(*(_bounded(job) for job in jobs), return_exceptions=True)
    results: list[JobRecord] = []
    for job, item in zip(jobs, raw, strict=True):
        if isinstance(item, asyncio.CancelledError):
            raise item
        if isinstance(item, BaseException):
            existing = await deps.job_repo.get(job.job_id)
            failed = JobRecord(
                job_id=job.job_id,
                request_id=job.request_id,
                form_id=job.form_id,
                status="failed",
                cursor=existing.cursor if existing is not None else JobCursor(slice_index=-1),
                document=None,
                summary=existing.summary if existing is not None else {},
                unverified=existing.unverified if existing is not None else [],
                failure_detail=f"{type(item).__name__}: {item}",
            )
            await deps.job_repo.put(failed)
            results.append(failed)
        else:
            results.append(item)
    return _settle(record, results)


def _settle(record: RequestRecord, results: list[JobRecord]) -> RequestResult:
    documents = [r.document for r in results if r.status == "done" and r.document is not None]
    failed_forms = [r.form_id for r in results if r.status != "done"]

    unverified: list[str] = []
    summary: dict[str, int] = {}
    for r in results:
        unverified.extend(r.unverified)
        for verdict, count in r.summary.items():
            summary[verdict] = summary.get(verdict, 0) + count

    status: Literal["done", "partial", "failed"]
    if not failed_forms:
        status = "done"
    elif len(failed_forms) == len(results):
        status = "failed"
    else:
        status = "partial"

    return RequestResult(
        request_id=record.request_id,
        status=status,
        documents=documents,
        requirements=record.requirements,
        summary=summary,
        unverified=unverified,
        failed_forms=failed_forms,
    )
