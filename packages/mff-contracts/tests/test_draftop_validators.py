"""DraftOp field combinations are valid per `kind`: append needs section_id, set/delete need
entry_id."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mff_contracts import DraftOp


def test_append_with_section_id_is_valid() -> None:
    op = DraftOp(kind="append", requirement_id="R-02", section_id="sec-1", value="four seats")
    assert op.section_id == "sec-1"
    assert op.entry_id is None


def test_append_without_section_id_is_rejected() -> None:
    with pytest.raises(ValidationError, match=r"append.*requires section_id"):
        DraftOp(kind="append", requirement_id="R-02", section_id=None)


def test_append_with_entry_id_is_rejected() -> None:
    with pytest.raises(ValidationError, match=r"append.*must not set entry_id"):
        DraftOp(kind="append", requirement_id="R-02", section_id="sec-1", entry_id="e-1")


@pytest.mark.parametrize("kind", ["set", "delete"])
def test_set_and_delete_with_entry_id_are_valid(kind: str) -> None:
    op = DraftOp(kind=kind, requirement_id="R-02", entry_id="e-1")
    assert op.entry_id == "e-1"
    assert op.section_id is None


@pytest.mark.parametrize("kind", ["set", "delete"])
def test_set_and_delete_without_entry_id_are_rejected(kind: str) -> None:
    with pytest.raises(ValidationError, match="requires entry_id"):
        DraftOp(kind=kind, requirement_id="R-02", entry_id=None)


@pytest.mark.parametrize("kind", ["set", "delete"])
def test_set_and_delete_with_section_id_are_rejected(kind: str) -> None:
    with pytest.raises(ValidationError, match="must not set section_id"):
        DraftOp(kind=kind, requirement_id="R-02", entry_id="e-1", section_id="sec-1")
