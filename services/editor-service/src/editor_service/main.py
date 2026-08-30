"""App factory. Nothing but wiring — see `vision_stub.main` for the sibling pattern this
mirrors."""

from __future__ import annotations

from fastapi import FastAPI

from editor_service.api.routers import health, slices

__all__ = ["create_app"]


def create_app() -> FastAPI:
    app = FastAPI(
        title="Editor service",
        version="0.0.0",
        description=(
            "The only service in the repo that calls a model (B8). Reviews derivative "
            "forms and composes net-new ones, one slice of requirements at a time."
        ),
    )
    app.include_router(health.router)
    app.include_router(slices.router)
    return app


app = create_app()
