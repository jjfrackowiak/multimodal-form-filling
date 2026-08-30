"""`GET /healthz` — must never construct a model client (B8 brief, DoD 7).

Imports nothing from `editor_service.llm` and nothing from `editor_service.settings`: a
health check must not cost a token, and must not fail because ADC or `GOOGLE_CLOUD_PROJECT`
are misconfigured on a box that is otherwise up.
"""

from __future__ import annotations

from fastapi import APIRouter

__all__ = ["router"]

router = APIRouter(tags=["ops"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
