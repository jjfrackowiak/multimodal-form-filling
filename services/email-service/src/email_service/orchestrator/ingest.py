"""Lift intake's `ParsedJob` into a `JobRequest` (blobs on GCS/in-memory)."""

from __future__ import annotations

from email_service.intake import ParsedRequest
from mff_contracts import BlobStore, JobImage, JobRequest, Mode, Requirement

__all__ = ["jobs_from_parsed"]

_DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


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
            jobs.append(
                JobRequest(
                    job_id=job_id,
                    request_id=request_id,
                    mode=Mode.DERIVATIVE,
                    form_id=parsed_job.form_id,
                    form=form,
                    requirements=requirements,
                    images=[],
                )
            )
            continue
        assert parsed_job.inputs is not None
        images: list[JobImage] = []
        for attachment in parsed_job.inputs.images:
            blob = await blobs.put(
                attachment.data,
                content_type=attachment.content_type or "application/octet-stream",
                kind="image",
            )
            images.append(
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
                images=images,
            )
        )
    return jobs
