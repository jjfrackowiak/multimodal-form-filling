"""Compile — the renderability check the orchestrator owns.

"Every comment anchors to something that still exists" is answered by
`mff_docmodel.attach_comments` itself: it returns which comment ids fell back to the
document-level anchor (`unanchored`) because their target id was missing from the
`RenderMap`. This module's job is only to call it and surface that list — reading the
editor's own answer, not re-deriving it, which is why this is not a second copy of the
editor's anchoring rules.
"""

from __future__ import annotations

from mff_contracts import (
    Artifact,
    BlobStore,
    CompiledForm,
    DerivativeArtifact,
    JobRequest,
    NetNewArtifact,
)
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
        assert isinstance(artifact, NetNewArtifact)
        _fill_notes(artifact, job)
        image_bytes, extra = await _netnew_images(job, artifact, blob_store)
        raw, render_map = compile_netnew(
            artifact,
            title="Vehicle return report",
            image_bytes=image_bytes,
            vehicle_fields=_vehicle_fields(job),
            extra_images=extra,
        )

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


async def _netnew_images(
    job: JobRequest, artifact: NetNewArtifact, blob_store: BlobStore
) -> tuple[dict[str, bytes], list[tuple[str, bytes]]]:
    used = {
        image.sha256
        for section in artifact.draft.sections
        for entry in section.entries
        for image in entry.images
    }
    image_bytes: dict[str, bytes] = {}
    extra: list[tuple[str, bytes]] = []
    for image in job.images:
        data = await blob_store.get(image.blob)
        image_bytes[image.blob.sha256] = data
        if image.blob.sha256 not in used:
            extra.append((image.original_filename, data))
    for section in artifact.draft.sections:
        for entry in section.entries:
            for ref in entry.images:
                if ref.sha256 not in image_bytes:
                    image_bytes[ref.sha256] = await blob_store.get(ref)
    return image_bytes, extra


def _fill_notes(artifact: NetNewArtifact, job: JobRequest) -> None:
    texts = job.inputs.texts if job.inputs is not None else {}
    notes = [
        content.strip()
        for name, content in texts.items()
        if "uwagi" in name.lower() or "note" in name.lower()
        if content.strip()
    ]
    if not notes:
        return
    blob = "\n".join(notes)
    for section in artifact.draft.sections:
        if section.id != "section-09":
            continue
        for entry in section.entries:
            if not entry.value:
                entry.value = blob
                return
        if section.entries:
            section.entries[0].value = (section.entries[0].value or "") or blob


def _vehicle_fields(job: JobRequest) -> list[tuple[str, str]]:
    texts = job.inputs.texts if job.inputs is not None else {}
    blob = "\n".join(
        content
        for name, content in texts.items()
        if "uwagi" not in name.lower() and "note" not in name.lower()
    )
    fields: list[tuple[str, str]] = []
    for line in blob.splitlines():
        line = line.strip()
        if not line:
            continue
        lower = line.lower()
        if lower.startswith("reg"):
            value = (
                line.split(".", 1)[-1].strip() if "." in line else line.split(":", 1)[-1].strip()
            )
            fields.append(("Registration number", value))
        elif ":" in line:
            label, value = line.split(":", 1)
            fields.append((label.strip(), value.strip()))
        elif not any(label == "Make and model" for label, _ in fields):
            fields.append(("Make and model", line))
    return fields
