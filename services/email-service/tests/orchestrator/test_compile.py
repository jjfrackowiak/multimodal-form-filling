"""Unit tests for `orchestrator.compile` — the renderability check: every comment
anchors to something that still exists, and the ones that don't are surfaced rather
than silently dropped.
"""

from __future__ import annotations

from mff_contracts import Anchor, DerivativeArtifact, NetNewArtifact, ReviewComment
from mff_store.memory import InMemoryBlobStore

from factories import make_derivative_job, make_netnew_job
from email_service.orchestrator.artifacts import build_initial_artifact
from email_service.orchestrator.compile import compile_job


async def test_compile_derivative_with_real_anchors_reports_nothing_unanchored() -> None:
    blob_store = InMemoryBlobStore()
    job = await make_derivative_job(blob_store)
    artifact = await build_initial_artifact(job, blob_store)
    assert isinstance(artifact, DerivativeArtifact)
    real_node_id = artifact.nodes[0].id
    artifact = artifact.model_copy(
        update={
            "comments": [
                ReviewComment(
                    requirement_id="R-01",
                    anchor=Anchor(kind="node", target_id=real_node_id),
                    verdict="pass",
                    justification="anchored to a real node",
                )
            ]
        }
    )

    compiled = await compile_job(job, artifact, blob_store, author="Test Author")

    assert compiled.unanchored == []
    assert compiled.comments_attached == 1
    assert compiled.document.size_bytes > 0


async def test_compile_derivative_with_a_dangling_anchor_is_surfaced_as_unanchored() -> None:
    blob_store = InMemoryBlobStore()
    job = await make_derivative_job(blob_store)
    artifact = await build_initial_artifact(job, blob_store)
    assert isinstance(artifact, DerivativeArtifact)
    artifact = artifact.model_copy(
        update={
            "comments": [
                ReviewComment(
                    requirement_id="R-01",
                    anchor=Anchor(kind="node", target_id="node-that-does-not-exist"),
                    verdict="pass",
                    justification="anchored to nothing real — renderability must catch this",
                )
            ]
        }
    )

    compiled = await compile_job(job, artifact, blob_store, author="Test Author")

    assert compiled.unanchored == ["R-01"]
    assert compiled.comments_attached == 1  # still attached — via the fallback run


async def test_compile_net_new_produces_a_document() -> None:
    job = make_netnew_job()
    blob_store = InMemoryBlobStore()
    artifact = await build_initial_artifact(job, blob_store)
    assert isinstance(artifact, NetNewArtifact)
    artifact = artifact.model_copy(
        update={
            "comments": [
                ReviewComment(
                    requirement_id="R-01",
                    anchor=Anchor(kind="document"),
                    verdict="realised",
                    justification="composed from the client's inputs",
                )
            ]
        }
    )

    compiled = await compile_job(job, artifact, blob_store, author="Test Author")

    assert compiled.comments_attached == 1
    assert compiled.document.size_bytes > 0
