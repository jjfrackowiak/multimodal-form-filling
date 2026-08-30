"""Compile — the renderability check the orchestrator owns.

"Every comment anchors to something that still exists" is answered by
`mff_docmodel.attach_comments` itself: it returns which comment ids fell back to the
document-level anchor (`unanchored`) because their target id was missing from the
`RenderMap`. This module's job is only to call it and surface that list — reading the
editor's own answer, not re-deriving it, which is why this is not a second copy of the
editor's anchoring rules.
"""

from __future__ import annotations

from mff_contracts import Artifact, BlobStore, CompiledForm, DerivativeArtifact, JobRequest
from mff_docmodel import attach_comments, compile_derivative, compile_netnew

__all__ = ["DOCX_CONTENT_TYPE", "compile_job"]

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


async def compile_job(
    job: JobRequest, artifact: Artifact, blob_store: BlobStore, *, author: str
) -> CompiledForm:
    if isinstance(artifact, DerivativeArtifact):
        source = await blob_store.get(artifact.source)
        raw, render_map = compile_derivative(artifact, source)
    else:
        raw, render_map = compile_netnew(artifact)

    rendered, attached, unanchored = attach_comments(
        raw, artifact.comments, render_map, author=author
    )
    document = await blob_store.put(rendered, content_type=DOCX_CONTENT_TYPE, kind="output")
    return CompiledForm(
        form_id=job.form_id,
        document=document,
        render_map=render_map,
        comments_attached=attached,
        unanchored=unanchored,
    )
