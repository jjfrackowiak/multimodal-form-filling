"""Thin HTTP layer: parse, delegate, return. No domain logic lives here."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from vision_stub.api.deps import get_analysis_service
from vision_stub.api.schemas import InventoryRequest, InventoryResponse
from vision_stub.services.analysis import AnalysisService

__all__ = ["router"]

router = APIRouter(prefix="/v1", tags=["vision"])


@router.post("/inventory", response_model=InventoryResponse)
async def build_inventory(
    body: InventoryRequest,
    svc: AnalysisService = Depends(get_analysis_service),
) -> InventoryResponse:
    """Classify a job's images against what its requirements are looking for.

    One call per job. The result is index-aligned with the request.
    """
    return InventoryResponse(images=await svc.build_inventory(body.images, body.requirements))
