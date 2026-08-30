"""`POST /manifest:parse` — editor parses the manifest once (req 7)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from mff_contracts import Requirement
from mff_manifest import parse_manifest

__all__ = ["router"]

router = APIRouter(tags=["manifest"])


class ManifestParseRequest(BaseModel):
    raw: str


class ManifestParseResponse(BaseModel):
    requirements: list[Requirement]


@router.post("/manifest:parse", response_model=ManifestParseResponse)
async def parse_manifest_endpoint(body: ManifestParseRequest) -> ManifestParseResponse:
    from editor_service.llm.extractor import VertexJsonExtractor

    manifest = await parse_manifest(body.raw, extractor=VertexJsonExtractor())
    return ManifestParseResponse(requirements=manifest.requirements)
