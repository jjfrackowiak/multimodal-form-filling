"""Dependency providers. Injected via Depends so a test can substitute a service
pointed at a different inventory."""

from __future__ import annotations

from functools import lru_cache

from vision_stub.services.analysis import AnalysisService

__all__ = ["get_analysis_service"]


@lru_cache(maxsize=1)
def get_analysis_service() -> AnalysisService:
    return AnalysisService()
