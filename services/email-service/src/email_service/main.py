"""ASGI entrypoint for the email service."""

from __future__ import annotations

from fastapi import FastAPI

__all__ = ["app", "create_app"]


def create_app() -> FastAPI:
    app = FastAPI(title="Email service", version="0.0.0")

    @app.get("/healthz", tags=["ops"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
