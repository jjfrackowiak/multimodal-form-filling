"""Thin HTTP layer: parse, delegate, return. No domain logic lives here."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from ffx_vision import ImageAnalysis, ImageRef
from pydantic import BaseModel

from vision_stub.api.deps import get_analysis_service
from vision_stub.api.schemas import BatchRequest, CropRequest, DescribeRequest
from vision_stub.services.analysis import AnalysisService

__all__ = ["router"]

router = APIRouter(prefix="/v1", tags=["vision"])


class BatchResponse(BaseModel):
    results: list[ImageAnalysis]


@router.post("/describe", response_model=ImageAnalysis)
async def describe(
    body: DescribeRequest,
    svc: AnalysisService = Depends(get_analysis_service),
) -> ImageAnalysis:
    return await svc.describe(body.ref)


@router.post("/describe:batch", response_model=BatchResponse)
async def describe_batch(
    body: BatchRequest,
    svc: AnalysisService = Depends(get_analysis_service),
) -> BatchResponse:
    return BatchResponse(results=await svc.describe_many(body.refs))


@router.post("/crop", response_model=ImageRef)
async def crop(
    body: CropRequest,
    svc: AnalysisService = Depends(get_analysis_service),
) -> ImageRef:
    return await svc.crop(body.ref, body.box)
