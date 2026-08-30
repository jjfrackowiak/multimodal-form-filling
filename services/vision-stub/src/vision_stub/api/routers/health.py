from __future__ import annotations

from fastapi import APIRouter

__all__ = ["router"]

router = APIRouter(tags=["ops"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    # Names itself a placeholder so nobody mistakes a green healthcheck for
    # working image understanding.
    return {"status": "ok", "implementation": "placeholder"}
