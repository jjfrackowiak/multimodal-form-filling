"""App factory."""

from __future__ import annotations

from fastapi import FastAPI

from editor_service.api.routers import health, manifest, slices

__all__ = ["create_app"]


def create_app() -> FastAPI:
    app = FastAPI(
        title="Editor service",
        version="0.0.0",
        description=(
            "The only service in the repo that calls a model (B8). Reviews derivative "
            "forms and composes net-new ones, one slice of requirements at a time. "
            "Calls CV at slice time for photo inventory."
        ),
    )
    app.include_router(health.router)
    app.include_router(slices.router)
    app.include_router(manifest.router)
    return app


app = create_app()
