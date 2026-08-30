"""No logic yet (B0 is a skeleton) — just proves the package installs and imports cleanly."""

from __future__ import annotations

import mff_docmodel


def test_package_imports_with_no_public_surface_yet() -> None:
    assert mff_docmodel.__all__ == []
