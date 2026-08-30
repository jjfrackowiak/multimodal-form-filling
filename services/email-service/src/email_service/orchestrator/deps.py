"""What `run_job`/`run_request` are dispatched against.

One place to wire a real deployment (Firestore/GCS adapters, an HTTP `SliceRunner`) or
a test double (in-memory adapters, `runner.fake.FakeSliceRunner`) without changing
either function's signature.
"""

from __future__ import annotations

from dataclasses import dataclass

from email_service.runner import SliceRunner
from mff_contracts import ArtifactRepository, BlobStore, JobRepository

__all__ = ["OrchestratorDeps"]


@dataclass(frozen=True, slots=True)
class OrchestratorDeps:
    artifact_repo: ArtifactRepository
    job_repo: JobRepository
    blob_store: BlobStore
    runner: SliceRunner
    comment_author: str = "MFF Reviewer"
    # req 11: bound the concurrency of parallel jobs — interdependence never crosses
    # forms, but the editor service (and its model calls) is not free to fan out on.
    max_concurrent_jobs: int = 4
