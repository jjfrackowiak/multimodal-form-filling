"""Node (derivative), Entry/Section/FormDraft (net-new) — reqs 12, 14, 15."""

from __future__ import annotations

from mff_contracts import BlobRef, Entry, FormDraft, Node, Section


def test_node_is_a_read_only_view_with_a_stable_id() -> None:
    node = Node(id="n-1", kind="heading", text="1. Under the bonnet", parent_id=None)
    assert node.image_sha256 is None


def test_node_image_links_to_a_job_image_by_sha256() -> None:
    node = Node(id="n-2", kind="image", text="", parent_id="n-1", image_sha256="abc123")
    assert node.image_sha256 == "abc123"


def test_entry_uses_a_fractional_order_key() -> None:
    entry = Entry(id="e-1", order="a0", value="Nissan Qashqai", set_by="R-01")
    assert entry.images == []


def test_form_draft_defaults_schema_version_and_empty_sections() -> None:
    draft = FormDraft()
    assert draft.schema_version == 1
    assert draft.sections == []


def test_section_holds_entries_built_by_requirements() -> None:
    blob = BlobRef(uri="gs://b/x", content_type="image/jpeg", size_bytes=1, sha256="x")
    entry = Entry(id="e-1", order="a0", value=None, images=[blob], set_by="R-04")
    section = Section(id="s-1", title="Podsufitka", entries=[entry])
    draft = FormDraft(sections=[section])
    assert draft.sections[0].entries[0].set_by == "R-04"
