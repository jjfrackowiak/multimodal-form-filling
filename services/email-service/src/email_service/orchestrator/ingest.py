"""Lift intake's `ParsedJob` into a `JobRequest` (blobs on GCS/in-memory)."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from email_service.intake import ParsedRequest
from mff_contracts import BlobStore, JobImage, JobRequest, Mode, Requirement

__all__ = ["jobs_from_parsed"]

_DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _sniff_image_type(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _embedded_rasters(docx: bytes) -> list[tuple[str, bytes, str]]:
    """JPEG/PNG/WebP parts under `word/media/` — the client's photos, already in the form."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(docx))
    except zipfile.BadZipFile:
        return []
    found: list[tuple[str, bytes, str]] = []
    with archive:
        for name in archive.namelist():
            if not name.startswith("word/media/") or name.endswith("/"):
                continue
            data = archive.read(name)
            content_type = _sniff_image_type(data)
            if content_type is None:
                continue
            found.append((Path(name).name, data, content_type))
    return found


async def jobs_from_parsed(
    parsed: ParsedRequest,
    *,
    request_id: str,
    requirements: list[Requirement],
    blobs: BlobStore,
) -> list[JobRequest]:
    jobs: list[JobRequest] = []
    for index, parsed_job in enumerate(parsed.jobs, start=1):
        job_id = f"{request_id}-{index:02d}"
        if parsed_job.mode is Mode.DERIVATIVE:
            assert parsed_job.form is not None
            form = await blobs.put(parsed_job.form.data, content_type=_DOCX_TYPE, kind="source")
            embedded_images: list[JobImage] = []
            for filename, data, content_type in _embedded_rasters(parsed_job.form.data):
                blob = await blobs.put(data, content_type=content_type, kind="image")
                embedded_images.append(
                    JobImage(
                        blob=blob,
                        original_filename=filename,
                        source="embedded",
                    )
                )
            jobs.append(
                JobRequest(
                    job_id=job_id,
                    request_id=request_id,
                    mode=Mode.DERIVATIVE,
                    form_id=parsed_job.form_id,
                    form=form,
                    requirements=requirements,
                    images=embedded_images,
                )
            )
            continue
        assert parsed_job.inputs is not None
        attachment_images: list[JobImage] = []
        for attachment in parsed_job.inputs.images:
            blob = await blobs.put(
                attachment.data,
                content_type=attachment.content_type or "application/octet-stream",
                kind="image",
            )
            attachment_images.append(
                JobImage(
                    blob=blob,
                    original_filename=attachment.filename,
                    source="attachment",
                )
            )
        jobs.append(
            JobRequest(
                job_id=job_id,
                request_id=request_id,
                mode=Mode.NET_NEW,
                form_id=parsed_job.form_id,
                inputs=parsed_job.inputs.inputs,
                requirements=requirements,
                images=attachment_images,
            )
        )
    return jobs
