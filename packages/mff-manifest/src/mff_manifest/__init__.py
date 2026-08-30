"""mff-manifest — free text into `Requirement[]` (req 5).

Req 5 calls this "a simple parsing / normalisation step"; the fleet-vehicle-return fixture
is the proof it is not. Two stages get you there: a deterministic pre-split (`presplit`,
line/paragraph boundaries, cheap and reproducible) and one small model call per chunk
behind the `RequirementExtractor` Protocol (`parse_manifest`), whose implementation lives
in the editor service — the only place in the system that owns model access.

This package imports no agent framework and no model library, `google` included — see
`tests/test_import_boundary.py`.
"""

from __future__ import annotations

from .errors import ManifestParseError, NonVerbatimSpanError
from .parser import DEFAULT_MAX_ATTEMPTS, parse_manifest
from .presplit import TextChunk, presplit
from .protocol import RequirementExtractor

__all__ = [
    "DEFAULT_MAX_ATTEMPTS",
    "ManifestParseError",
    "NonVerbatimSpanError",
    "RequirementExtractor",
    "TextChunk",
    "parse_manifest",
    "presplit",
]
