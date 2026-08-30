"""`POST /slices:run` — `SliceRequest` in, `SliceReport` out. Thin HTTP layer: parse,
delegate to the injected runner, return. No retry or validation logic lives here — that is
`editor_service.llm.run_slice`'s job (see `api/deps.py` for how the two are wired)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from editor_service.api.deps import SliceRunner, get_slice_runner
from mff_contracts import SliceReport, SliceRequest

__all__ = ["router"]

router = APIRouter(tags=["slices"])


@router.post("/slices:run", response_model=SliceReport)
async def run_slice_endpoint(
    body: SliceRequest,
    runner: SliceRunner = Depends(get_slice_runner),
) -> SliceReport:
    return await runner(body)
