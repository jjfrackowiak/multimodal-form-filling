"""`run_job` — one job's life: sequential slices, atomic commit+advance, resume from
cursor, completeness after the last slice, compile, done/failed.

Retry is deliberately absent. `SliceRunner.run` returns a `SliceReport` that is always
well-formed by the time it gets here (see `runner.protocol`) — complete, or
complete-with-`unverified` — so it is applied as-is; there is no pending/history/
validator-error state to loop on. `ArtifactRepository.save` commits the artifact and
advances the cursor as one transaction (`mff_store`'s guarantee), so a crash between
the two leaves neither written. Calling `run_job` again with the same `job_id` is the
entire recovery story: `load` returns exactly what was last committed and the loop
resumes at the next slice — nothing here retries a slice that already landed, and
nothing skips one that did not.

`failed` is reserved for what a re-run cannot fix: the completeness check finding a
requirement with no comment anywhere in the job, after every slice has already run.
"""

from __future__ import annotations

from typing import Literal

from mff_applier import apply_slice
from mff_contracts import (
    Artifact,
    BlobRef,
    JobCursor,
    JobRecord,
    JobRequest,
    Manifest,
    SliceRequest,
)
from mff_store.errors import NotFoundError

from .artifacts import build_initial_artifact, scope_ids_for
from .compile import compile_job
from .completeness import missing_requirement_ids
from .deps import OrchestratorDeps

__all__ = ["run_job"]

# JobRecord.cursor before any slice has committed for this job. -1 is not a valid
# slice index (JobCursor.slice_index is 0-based), so it cannot be confused with "slice
# 0 committed".
_NO_SLICE_COMMITTED = JobCursor(slice_index=-1)


async def run_job(job: JobRequest, deps: OrchestratorDeps) -> JobRecord:
    plan = Manifest(raw="", requirements=job.requirements).slices()
    requirements_by_id = {requirement.id: requirement for requirement in job.requirements}

    try:
        artifact, cursor, version = await deps.artifact_repo.load(job.job_id)
        next_index = cursor.slice_index + 1
    except NotFoundError:
        artifact = await build_initial_artifact(job, deps.blob_store)
        version = 0
        next_index = 0
        cursor = _NO_SLICE_COMMITTED

    await deps.job_repo.put(_record(job, "running", cursor, unverified=_unverified_ids(artifact)))

    for index in range(next_index, len(plan)):
        slice_plan = plan[index]
        requirements = [requirements_by_id[rid] for rid in slice_plan.requirement_ids]
        scope_ids = scope_ids_for(artifact)

        report = await deps.runner.run(
            SliceRequest(
                job_id=job.job_id,
                slice_id=slice_plan.slice_id,
                mode=job.mode,
                requirements=requirements,
                artifact=artifact,
                scope_ids=scope_ids,
            )
        )
        # Accepted as-is — no retry loop. See the module docstring.
        result = apply_slice(artifact, report, scope_ids)
        artifact = result.artifact
        cursor = JobCursor(slice_index=index)
        version = await deps.artifact_repo.save(artifact, cursor, expected_version=version)
        await deps.job_repo.put(
            _record(job, "running", cursor, unverified=_unverified_ids(artifact))
        )

    missing = missing_requirement_ids(job.requirements, artifact.comments)
    if missing:
        record = _record(
            job,
            "failed",
            cursor,
            unverified=_unverified_ids(artifact),
            failure_detail=(
                "completeness check: no comment for requirement(s) " + ", ".join(sorted(missing))
            ),
        )
        await deps.job_repo.put(record)
        return record

    compiled = await compile_job(job, artifact, deps.blob_store, author=deps.comment_author)
    summary = _summary(artifact)
    summary["unanchored"] = len(compiled.unanchored)  # req 12/16: the renderability check
    record = _record(
        job,
        "done",
        cursor,
        unverified=_unverified_ids(artifact),
        document=compiled.document,
        summary=summary,
    )
    await deps.job_repo.put(record)
    return record


def _unverified_ids(artifact: Artifact) -> list[str]:
    return [
        comment.requirement_id for comment in artifact.comments if comment.verdict == "unverified"
    ]


def _summary(artifact: Artifact) -> dict[str, int]:
    summary: dict[str, int] = {}
    for comment in artifact.comments:
        summary[comment.verdict] = summary.get(comment.verdict, 0) + 1
    return summary


def _record(
    job: JobRequest,
    status: Literal["running", "done", "failed"],
    cursor: JobCursor,
    *,
    unverified: list[str],
    document: BlobRef | None = None,
    summary: dict[str, int] | None = None,
    failure_detail: str | None = None,
) -> JobRecord:
    return JobRecord(
        job_id=job.job_id,
        request_id=job.request_id,
        form_id=job.form_id,
        status=status,
        cursor=cursor,
        document=document,
        summary=summary or {},
        unverified=unverified,
        failure_detail=failure_detail,
    )
