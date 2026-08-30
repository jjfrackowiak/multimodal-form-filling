from __future__ import annotations

import pytest
from factories import load_requirements, load_review_comments
from mff_contracts import Requirement, ReviewComment


@pytest.fixture
def requirements() -> list[Requirement]:
    return load_requirements()


@pytest.fixture
def review_comments() -> dict[str, ReviewComment]:
    return load_review_comments()
