"""No logic yet (B0 is a skeleton) — just proves the package installs and imports cleanly."""

from __future__ import annotations

import editor_service


def test_package_imports_with_no_public_surface_yet() -> None:
    assert editor_service.__all__ == []
