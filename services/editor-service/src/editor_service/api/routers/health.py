"""`GET /healthz` — must never construct a model client (B8 brief, DoD 7).

This module imports neither the package that builds agents nor the one that resolves
configuration: a health check must not cost a token, and must not fail because ADC or a
project id are misconfigured on a box that is otherwise up.
"""

from __future__ import annotations

from fastapi import APIRouter

__all__ = ["router"]

router = APIRouter(tags=["ops"])


@router.get("/health")
@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
