"""Unit tests for `orchestrator.artifacts`: how a fresh `Artifact` comes into being,
and what a slice's `scope_ids` are for each mode.
"""

from __future__ import annotations

from factories import make_derivative_job, make_netnew_job

from email_service.orchestrator.artifacts import (
    build_initial_artifact,
    scope_ids_for,
)
from mff_contracts import DerivativeArtifact, NetNewArtifact
from mff_store.memory import InMemoryBlobStore


async def test_build_initial_derivative_artifact_parses_real_nodes() -> None:
    blob_store = InMemoryBlobStore()
    job = await make_derivative_job(blob_store)

    artifact = await build_initial_artifact(job, blob_store)

    assert isinstance(artifact, DerivativeArtifact)
    assert artifact.job_id == job.job_id
    assert artifact.form_id == job.job_id
    assert artifact.source == job.form
    assert artifact.comments == []
    assert len(artifact.nodes) > 0  # a real 2.8MB fixture .docx parses to real nodes


async def test_build_initial_net_new_artifact_seeds_report_scaffold() -> None:
    job = make_netnew_job()
    blob_store = InMemoryBlobStore()

    artifact = await build_initial_artifact(job, blob_store)

    assert isinstance(artifact, NetNewArtifact)
    assert artifact.job_id == job.job_id
    assert artifact.form_id == job.job_id
    assert artifact.comments == []
    assert [s.id for s in artifact.draft.sections] == [
        "section-01",
        "section-02",
        "section-03",
        "section-04",
        "section-05",
        "section-06",
        "section-07",
        "section-08",
        "section-09",
    ]
    assert {e.id for s in artifact.draft.sections for e in s.entries} == {
        f"entry-{r.id}" for r in job.requirements
    }


async def test_scope_ids_for_derivative_is_every_node_id() -> None:
    blob_store = InMemoryBlobStore()
    job = await make_derivative_job(blob_store)
    artifact = await build_initial_artifact(job, blob_store)
    assert isinstance(artifact, DerivativeArtifact)

    assert scope_ids_for(artifact) == [n.id for n in artifact.nodes]


async def test_scope_ids_for_net_new_is_every_section_id() -> None:
    job = make_netnew_job()
    blob_store = InMemoryBlobStore()
    artifact = await build_initial_artifact(job, blob_store)

    assert scope_ids_for(artifact) == [s.id for s in artifact.draft.sections]
