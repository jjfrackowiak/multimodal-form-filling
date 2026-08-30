"""`POST /slices:run` — `SliceRequest` in, `SliceReport` out. Thin HTTP layer: parse,
delegate to the injected runner, return. No retry or validation logic lives here — that is
`editor_service.llm.run_slice`'s job (see `api/deps.py` for how the two are wired)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from editor_service.api.deps import SliceRunner, get_slice_runner
from mff_contracts import SliceReport, SliceRequest
from mff_vision import VisionUnavailable

__all__ = ["router"]

router = APIRouter(tags=["slices"])


@router.post("/slices:run", response_model=SliceReport)
async def run_slice_endpoint(
    body: SliceRequest,
    runner: SliceRunner = Depends(get_slice_runner),
) -> SliceReport:
    try:
        return await runner(body)
    except VisionUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
