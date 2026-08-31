"""orchestrator — a job's life, from `JobRequest` to a settled `RequestResult`.

    Request                     one client email — the body is the manifest
      └── Job  (one work item)  ← PARALLEL, semaphore-bounded (`run_request`)
            └── Slice           ← SEQUENTIAL, in ordinal order (`run_job`)

`run_job` walks one job's slices in order, committing artifact+cursor atomically after
each (`ArtifactRepository.save`) and resuming from the persisted cursor rather than
retrying from scratch on a crash. `run_request` fans a request's jobs out concurrently,
bounded by a semaphore, and holds the delivery barrier: one `RequestResult` once every
job has settled.
"""

from __future__ import annotations

from .artifacts import NET_NEW_ROOT_SECTION_ID, build_initial_artifact, scope_ids_for
from .compile import compile_job
from .completeness import missing_requirement_ids
from .deps import OrchestratorDeps
from .ingest import jobs_from_parsed
from .job import run_job
from .request import run_request

__all__ = [
    "NET_NEW_ROOT_SECTION_ID",
    "OrchestratorDeps",
    "build_initial_artifact",
    "compile_job",
    "jobs_from_parsed",
    "missing_requirement_ids",
    "run_job",
    "run_request",
    "scope_ids_for",
]
