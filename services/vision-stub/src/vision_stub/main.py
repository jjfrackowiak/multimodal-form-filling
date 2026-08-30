"""App factory. Nothing but wiring."""

from __future__ import annotations

from fastapi import FastAPI

from vision_stub.api.routers import analyse, health

__all__ = ["create_app"]


def create_app() -> FastAPI:
    app = FastAPI(
        title="Vision service (placeholder)",
        version="0.0.0",
        description=(
            "Stands in for image understanding (req 13). Takes a job's images and "
            "what its requirements are looking for; answers with an inventory of what "
            "each image shows. Reads the fleet fixture's labels; processes no pixels."
        ),
    )
    app.include_router(health.router)
    app.include_router(analyse.router)
    return app


app = create_app()
