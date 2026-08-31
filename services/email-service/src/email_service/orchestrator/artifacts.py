"""How a job's `Artifact` comes into being before its first slice ever runs, and what
a slice is allowed to touch once it does.

Derivative: a read-only parse of the client's document (`mff_docmodel.parse_docx`).
Nothing here mutates the source bytes — `source` travels into the artifact unchanged,
exactly as req 14 (the client's document is never modified) requires.

Net-new: `DraftOp(kind="append"/"set")` targets an existing `Section.id` (`mff_applier`
rejects an op whose section is not already in the draft). The editor's composer scaffolds
one section per report heading plus one entry slot per requirement. This module must seed
the *same* draft, or the orchestrator compiles the empty one-section stub and Word gets a
job-id title with no body.

`Artifact.form_id` is set to `job.job_id` here, not `job.form_id` — mff-store keys
`ArtifactRepository` by `form_id`. The human-readable label still lives on `JobRecord`
and is passed to `compile_netnew` as the document title.
"""

from __future__ import annotations

from mff_contracts import (
    Artifact,
    BlobStore,
    DerivativeArtifact,
    JobRequest,
    Mode,
    NetNewArtifact,
)
from mff_docmodel import SCAFFOLD_SECTIONS, netnew_scaffold, parse_docx

__all__ = ["NET_NEW_ROOT_SECTION_ID", "build_initial_artifact", "scope_ids_for"]

NET_NEW_ROOT_SECTION_ID = SCAFFOLD_SECTIONS[0][0]


async def build_initial_artifact(job: JobRequest, blob_store: BlobStore) -> Artifact:
    if job.mode == Mode.DERIVATIVE:
        assert job.form is not None  # JobRequest's own validator guarantees this
        source_bytes = await blob_store.get(job.form)
        nodes = parse_docx(source_bytes)
        return DerivativeArtifact(
            job_id=job.job_id, form_id=job.job_id, source=job.form, nodes=nodes, comments=[]
        )

    assert job.inputs is not None  # JobRequest's own validator guarantees this
    return NetNewArtifact(
        job_id=job.job_id,
        form_id=job.job_id,
        draft=netnew_scaffold(job.requirements),
        comments=[],
    )


def scope_ids_for(artifact: Artifact) -> list[str]:
    """Node ids (derivative) or section ids (net-new) a slice's `DraftOp`s may target.

    Only net-new mode's `apply_slice` actually consults this — a derivative report's
    `ops` must be empty by construction (req 14), so `scope_ids` is inert there. Every
    current node id is still the most honest value to hand back for a derivative slice,
    since it is exactly what that slice could legitimately anchor a comment to.
    """
    if isinstance(artifact, DerivativeArtifact):
        return [node.id for node in artifact.nodes]
    return [section.id for section in artifact.draft.sections]
