from __future__ import annotations

from pathlib import Path

import pytest

_RELATIVE_DERIVATIVE = Path("fixtures/fleet-vehicle-return/input/derivative/form_supplied.docx")
_RELATIVE_NETNEW_IMAGES = Path("fixtures/fleet-vehicle-return/input/netnew/WN-7020U")


def _find(relative: Path) -> Path:
    """Walk up from this file to the repo root that holds `fixtures/`.

    Installed as a wheel there is no fixed relative depth to the fixture; a fixed
    `../../..` is wrong the moment this file moves. Mirrors `mff_vision.mock.default_inventory`.
    """
    for parent in Path(__file__).resolve().parents:
        candidate = parent / relative
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"fixture not found by walking up from {__file__}: {relative}")


@pytest.fixture(scope="session")
def derivative_docx_path() -> Path:
    return _find(_RELATIVE_DERIVATIVE)


@pytest.fixture(scope="session")
def derivative_docx_bytes(derivative_docx_path: Path) -> bytes:
    return derivative_docx_path.read_bytes()


@pytest.fixture(scope="session")
def netnew_images_dir() -> Path:
    return _find(_RELATIVE_NETNEW_IMAGES)
