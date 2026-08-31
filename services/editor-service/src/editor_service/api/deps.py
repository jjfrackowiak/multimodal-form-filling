"""Dependency providers for the HTTP surface.

`get_slice_runner` dispatches to B6 (`review_derivative`) or B7 (`compose_netnew`).
The editor calls CV at slice time (`HttpVisionTool`) with the job's full checklist
and photos; inventory is cached per `job_id` so a second slice does not re-label.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable

from editor_service.flows.derivative import review_derivative
from editor_service.flows.netnew import compose_netnew
from mff_contracts import (
    DerivativeArtifact,
    ImageAnalysis,
    JobImage,
    Mode,
    NetNewArtifact,
    Requirement,
    RequirementSpec,
    SliceReport,
    SliceRequest,
)
from mff_vision import HttpVisionTool, ImageRef, VisionTool, VisionUnavailable

__all__ = ["SliceRunner", "get_slice_runner", "get_vision_tool"]

SliceRunner = Callable[[SliceRequest], Awaitable[SliceReport]]

_inventory_by_job: dict[str, list[ImageAnalysis]] = {}


def get_vision_tool() -> VisionTool | None:
    """CV base URL. Unset in unit tests that do not exercise vision."""
    url = (os.environ.get("CV_URL") or os.environ.get("VISION_SERVICE_URL") or "").rstrip("/")
    if not url:
        return None
    return HttpVisionTool(url)


def _specs(requirements: list[Requirement]) -> list[RequirementSpec]:
    return [RequirementSpec(id=r.id, text=r.text, constraint=r.constraint) for r in requirements]


def _uris(images: list[JobImage]) -> list[ImageRef]:
    return [ImageRef(uri=image.blob.uri) for image in images if image.blob.uri]


async def inventory_for(req: SliceRequest, vision: VisionTool | None = None) -> list[ImageAnalysis]:
    cached = _inventory_by_job.get(req.job_id)
    if cached is not None:
        return cached
    refs = _uris(req.images)
    if not refs:
        return []
    tool = vision if vision is not None else get_vision_tool()
    if tool is None:
        raise VisionUnavailable("CV_URL is not set")
    checklist = req.checklist or req.requirements
    inventory = await tool.build_inventory(refs, _specs(checklist))
    by_uri = {image.blob.uri: image.original_filename for image in req.images if image.blob.uri}
    inventory = [
        row.model_copy(update={"file": by_uri[row.uri]}) if row.uri in by_uri else row
        for row in inventory
    ]
    _inventory_by_job[req.job_id] = inventory
    return inventory


async def run_wired_slice(req: SliceRequest) -> SliceReport:
    inventory = await inventory_for(req)
    if req.mode is Mode.DERIVATIVE:
        if not isinstance(req.artifact, DerivativeArtifact):
            raise ValueError("derivative slice requires a DerivativeArtifact")
        return await review_derivative(req, req.artifact, inventory)
    if req.mode is Mode.NET_NEW:
        if not isinstance(req.artifact, NetNewArtifact):
            raise ValueError("net-new slice requires a NetNewArtifact")
        return await compose_netnew(req, req.artifact, inventory, req.client_texts)
    raise ValueError(f"unsupported mode {req.mode!r}")


def get_slice_runner() -> SliceRunner:
    return run_wired_slice
