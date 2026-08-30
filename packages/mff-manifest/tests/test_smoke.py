"""The package imports cleanly and exposes the surface the brief specifies."""

from __future__ import annotations

import mff_manifest


def test_public_surface() -> None:
    assert set(mff_manifest.__all__) == {
        "DEFAULT_MAX_ATTEMPTS",
        "ManifestParseError",
        "NonVerbatimSpanError",
        "RequirementExtractor",
        "TextChunk",
        "parse_manifest",
        "presplit",
    }
