"""Unit tests for `orchestrator.artifacts`: how a fresh `Artifact` comes into being,
and what a slice's `scope_ids` are for each mode.
"""

from __future__ import annotations

from factories import make_derivative_job, make_netnew_job

from email_service.orchestrator.artifacts import (
    NET_NEW_ROOT_SECTION_ID,
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


async def test_build_initial_net_new_artifact_seeds_one_section() -> None:
    job = make_netnew_job()
    blob_store = InMemoryBlobStore()

    artifact = await build_initial_artifact(job, blob_store)

    assert isinstance(artifact, NetNewArtifact)
    assert artifact.job_id == job.job_id
    assert artifact.form_id == job.job_id
    assert artifact.comments == []
    assert [s.id for s in artifact.draft.sections] == [NET_NEW_ROOT_SECTION_ID]
    assert artifact.draft.sections[0].entries == []


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

    assert scope_ids_for(artifact) == [NET_NEW_ROOT_SECTION_ID]
