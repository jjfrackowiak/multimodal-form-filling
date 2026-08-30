"""How a job's `Artifact` comes into being before its first slice ever runs, and what
a slice is allowed to touch once it does.

Derivative: a read-only parse of the client's document (`mff_docmodel.parse_docx`).
Nothing here mutates the source bytes — `source` travels into the artifact unchanged,
exactly as req 14 (the client's document is never modified) requires.

Net-new: `DraftOp(kind="append")` targets an existing `Section.id` (`mff_applier`
rejects an append whose section is not already in the draft), and nothing downstream
of this module mints one — no `DraftOp` kind creates a section. So a fresh net-new
artifact is seeded with exactly one section up front, scoped to every slice, which is
what makes the first slice's first append representable at all. This is a genuine
ambiguity in the brief (see the PR description): section *structure* for a composed
document is not modelled anywhere in `mff-contracts`, so "one section per job" is this
branch's own, deliberately minimal, choice rather than something the contract dictates.

`Artifact.form_id` is set to `job.job_id` here, not `job.form_id` — see the PR
description ("mff-store keys `ArtifactRepository` by `form_id`, not `job_id`"). The
`JobCursor`/`ArtifactRepository` protocol this branch is handed (`load(job_id)`) is
only correct, per `InMemoryArtifactRepository`'s own docstring, when the artifact's
`form_id` and the caller's `job_id` are the same string. Two different client forms
can legitimately share a filename or folder name across two jobs in the same request
(three derivative jobs literally do, in the mixed-request test), so `job.form_id`
cannot safely be the storage key; `job.job_id` is the one field this system already
guarantees is unique per job. The human-readable label (`job.form_id`) still reaches
`JobRecord.form_id` and `CompiledForm.form_id` untouched — the one place this leaks is
`compile_netnew`'s document heading, which will show a job id instead of the client's
own form label. That is a real, minor regression, and it belongs to the store's gap,
not to something fixable from this branch's owned directories.
"""

from __future__ import annotations

from mff_contracts import (
    Artifact,
    BlobStore,
    DerivativeArtifact,
    FormDraft,
    JobRequest,
    Mode,
    NetNewArtifact,
    Section,
)
from mff_docmodel import parse_docx

__all__ = ["NET_NEW_ROOT_SECTION_ID", "build_initial_artifact", "scope_ids_for"]

NET_NEW_ROOT_SECTION_ID = "draft"


async def build_initial_artifact(job: JobRequest, blob_store: BlobStore) -> Artifact:
    if job.mode == Mode.DERIVATIVE:
        assert job.form is not None  # JobRequest's own validator guarantees this
        source_bytes = await blob_store.get(job.form)
        nodes = parse_docx(source_bytes)
        return DerivativeArtifact(
            job_id=job.job_id, form_id=job.job_id, source=job.form, nodes=nodes, comments=[]
        )

    assert job.inputs is not None  # JobRequest's own validator guarantees this
    root = Section(id=NET_NEW_ROOT_SECTION_ID, title=job.form_id, entries=[])
    return NetNewArtifact(
        job_id=job.job_id, form_id=job.job_id, draft=FormDraft(sections=[root]), comments=[]
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
