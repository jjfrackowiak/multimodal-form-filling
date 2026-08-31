"""`POST /slices:run` — `SliceRequest` in, `SliceReport` out. Thin HTTP layer: parse,
delegate to the injected runner, return. No retry or validation logic lives here — that is
`editor_service.llm.run_slice`'s job (see `api/deps.py` for how the two are wired)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from editor_service.api.deps import SliceRunner, get_slice_runner
from mff_contracts import SliceReport, SliceRequest
from mff_vision import VisionUnavailable

__all__ = ["router"]

log = logging.getLogger("editor")
router = APIRouter(tags=["slices"])


@router.post("/slices:run", response_model=SliceReport)
async def run_slice_endpoint(
    body: SliceRequest,
    runner: SliceRunner = Depends(get_slice_runner),
) -> SliceReport:
    try:
        return await runner(body)
    except VisionUnavailable as exc:
        # Live 0d26c254afc6-02: CV /v1/inventory 200 then this 502, no traceback in logs.
        log.exception("slices:run vision unavailable job_id=%s", body.job_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
