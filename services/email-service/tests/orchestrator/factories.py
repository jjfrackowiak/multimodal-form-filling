"""Small builders for orchestrator tests, shared by every test module — mirrors
`packages/mff-store/tests/factories.py`.

Golden data comes straight from `fixtures/fleet-vehicle-return/` — `manifest.txt`,
`expected_requirements.yaml`, `expected_output/review.yaml` — not reproduced by hand,
mirroring `packages/mff-contracts/tests/test_manifest_slices.py`. That fixture gives
exactly the case the brief asks for: ten requirements chunking into two slices (6, 4),
plus a real derivative form and a real net-new input folder for the mixed-request test.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from mff_contracts import (
    Anchor,
    ClientInputs,
    Constraint,
    JobRequest,
    Mode,
    Requirement,
    ReviewComment,
    SliceReport,
    SliceRequest,
)
from mff_store.memory import (
    InMemoryArtifactRepository,
    InMemoryBlobStore,
    InMemoryJobRepository,
)

from email_service.orchestrator.deps import OrchestratorDeps
from email_service.runner.protocol import SliceRunner

__all__ = [
    "FIXTURE",
    "DOCX_CONTENT_TYPE",
    "RoutingSliceRunner",
    "load_requirements",
    "load_review_comments",
    "make_deps",
    "make_derivative_job",
    "make_netnew_job",
    "unique_id",
]

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _find_fixture_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "fixtures" / "fleet-vehicle-return"
        if candidate.exists():
            return candidate
    raise FileNotFoundError("fixtures/fleet-vehicle-return not found above this test file")


FIXTURE = _find_fixture_root()


def _build_constraint(entry: dict[str, object]) -> Constraint | None:
    raw = entry.get("constraint")
    if raw is None:
        return None
    assert isinstance(raw, dict)
    return Constraint(
        kind=raw["kind"],
        value=raw["value"],
        source_span=raw["constraint_source_span"],
        source_line=raw["constraint_source_line"],
        note=raw.get("note"),
    )


def load_requirements() -> list[Requirement]:
    """The fixture's ten requirements, R-01..R-10 — chunks into slices of 6 and 4."""
    data = yaml.safe_load((FIXTURE / "expected_requirements.yaml").read_text(encoding="utf-8"))
    requirements = []
    for entry in data["requirements"]:
        requirements.append(
            Requirement(
                id=entry["id"],
                ordinal=entry["ordinal"],
                text=entry["text"],
                source_span=entry["source_span"],
                source_line=entry["source_line"],
                expected_count=entry.get("expected_count", 1),
                constraint=_build_constraint(entry),
                ambiguity=entry.get("ambiguity"),
            )
        )
    return requirements


def load_review_comments() -> dict[str, ReviewComment]:
    """The fixture's golden verdicts, as `ReviewComment`s keyed by requirement id.

    Anchored `kind="document"` throughout — this fixture's `review.yaml` records
    verdicts, not node ids, and none of the orchestrator's own logic (sequencing,
    atomicity, completeness, the barrier) depends on where a comment is anchored.
    Anchoring specific runs is the editor's job (B6/B7/B8), not this branch's.
    """
    data = yaml.safe_load(
        (FIXTURE / "expected_output" / "review.yaml").read_text(encoding="utf-8")
    )
    comments: dict[str, ReviewComment] = {}
    for entry in data["verdicts"]:
        comments[entry["requirement_id"]] = ReviewComment(
            requirement_id=entry["requirement_id"],
            anchor=Anchor(kind="document"),
            verdict=entry["verdict"],
            justification=entry["justification"].strip(),
            suggestion=(entry.get("suggestion") or "").strip() or None,
        )
    return comments


async def make_derivative_job(
    blob_store: InMemoryBlobStore,
    *,
    job_id: str = "job-derivative-1",
    request_id: str = "req-1",
    form_id: str = "form_supplied.docx",
    requirements: list[Requirement] | None = None,
    source_bytes: bytes | None = None,
) -> JobRequest:
    """A derivative `JobRequest` for the fixture's real form, whose bytes are put into
    `blob_store` here so `build_initial_artifact` can `parse_docx` them later."""
    data = source_bytes or (FIXTURE / "input" / "derivative" / "form_supplied.docx").read_bytes()
    blob = await blob_store.put(data, content_type=DOCX_CONTENT_TYPE, kind="source")
    return JobRequest(
        job_id=job_id,
        request_id=request_id,
        mode=Mode.DERIVATIVE,
        form_id=form_id,
        form=blob,
        requirements=requirements if requirements is not None else load_requirements(),
        images=[],
    )


def make_netnew_job(
    *,
    job_id: str = "job-netnew-1",
    request_id: str = "req-1",
    form_id: str = "WN-7020U",
    requirements: list[Requirement] | None = None,
) -> JobRequest:
    folder = FIXTURE / "input" / "netnew" / "WN-7020U"
    texts = {p.name: p.read_text(encoding="utf-8") for p in folder.glob("*.txt")}
    return JobRequest(
        job_id=job_id,
        request_id=request_id,
        mode=Mode.NET_NEW,
        form_id=form_id,
        inputs=ClientInputs(set_id=form_id, texts=texts),
        requirements=requirements if requirements is not None else load_requirements(),
        images=[],
    )


@dataclass
class RoutingSliceRunner:
    """Routes each `SliceRequest` to a per-job `SliceRunner`, keyed by `job_id`.

    Lets one `run_request` test give different jobs different behaviour (e.g. one job
    whose fake drops a requirement, to prove the barrier settles the request
    `"partial"` rather than losing that failure among the others).
    """

    by_job_id: dict[str, SliceRunner] = field(default_factory=dict)

    async def run(self, request: SliceRequest) -> SliceReport:
        return await self.by_job_id[request.job_id].run(request)


def make_deps(
    *,
    runner: SliceRunner,
    artifact_repo: InMemoryArtifactRepository | None = None,
    job_repo: InMemoryJobRepository | None = None,
    blob_store: InMemoryBlobStore | None = None,
    max_concurrent_jobs: int = 4,
) -> OrchestratorDeps:
    return OrchestratorDeps(
        artifact_repo=artifact_repo or InMemoryArtifactRepository(),
        job_repo=job_repo or InMemoryJobRepository(),
        blob_store=blob_store or InMemoryBlobStore(),
        runner=runner,
        max_concurrent_jobs=max_concurrent_jobs,
    )


def unique_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"
