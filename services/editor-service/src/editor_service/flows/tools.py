"""Mutation tools for composing a net-new form draft."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from editor_service.llm.deps import EditorDeps
from mff_contracts import DraftOp, Entry, FormDraft, NetNewArtifact, Section

__all__ = ["make_tools"]


def make_tools(deps: EditorDeps) -> list[Callable[..., str]]:
    """Create ADK tools that mutate the net-new artifact held by ``deps``.

    ``requirement_id`` is optional for compatibility with the three-argument tool shape
    in the brief. Existing entries provide provenance for set/delete; append requires the
    model to provide it because a new entry has no prior requirement to inherit.
    """
    if not isinstance(deps.artifact, NetNewArtifact):
        raise TypeError("net-new mutation tools require a NetNewArtifact")

    draft = deps.artifact.draft

    def set_field(
        section_id: str,
        entry_id: str,
        value: str,
        requirement_id: str | None = None,
    ) -> str:
        """Set or overwrite a field in the draft."""
        found = _find_entry(draft, entry_id)
        if found is None:
            return f"error: unknown entry {entry_id!r}"
        section, index = found
        if section.id != section_id:
            return f"error: entry {entry_id!r} is not in section {section_id!r}"

        entry = section.entries[index]
        context = requirement_id or entry.set_by
        section.entries[index] = entry.model_copy(update={"value": value, "set_by": context})
        deps.op_log.append(
            DraftOp(
                kind="set",
                requirement_id=context,
                entry_id=entry_id,
                value=value,
            )
        )
        return "ok"

    def append_entry(
        section_id: str,
        label: str,
        value: str,
        requirement_id: str | None = None,
    ) -> str:
        """Add a new labelled entry to a section."""
        section = _find_section(draft, section_id)
        if section is None:
            return f"error: unknown section {section_id!r}"
        if not requirement_id:
            return "error: requirement_id is required when appending an entry"

        rendered = f"{label}: {value}" if label else value
        entry = Entry(
            id=f"entry-{uuid.uuid4().hex}",
            order=_order_after(section.entries[-1].order if section.entries else None),
            value=rendered,
            set_by=requirement_id,
        )
        section.entries.append(entry)
        deps.op_log.append(
            DraftOp(
                kind="append",
                requirement_id=requirement_id,
                section_id=section_id,
                value=rendered,
            )
        )
        return "ok"

    def delete_entry(
        section_id: str,
        entry_id: str,
        requirement_id: str | None = None,
    ) -> str:
        """Remove an entry from a section."""
        found = _find_entry(draft, entry_id)
        if found is None:
            return f"error: unknown entry {entry_id!r}"
        section, index = found
        if section.id != section_id:
            return f"error: entry {entry_id!r} is not in section {section_id!r}"

        entry = section.entries[index]
        context = requirement_id or entry.set_by
        del section.entries[index]
        deps.op_log.append(DraftOp(kind="delete", requirement_id=context, entry_id=entry_id))
        return "ok"

    return [set_field, append_entry, delete_entry]


def _find_section(draft: FormDraft, section_id: str) -> Section | None:
    return next((section for section in draft.sections if section.id == section_id), None)


def _find_entry(draft: FormDraft, entry_id: str) -> tuple[Section, int] | None:
    for section in draft.sections:
        for index, entry in enumerate(section.entries):
            if entry.id == entry_id:
                return section, index
    return None


def _order_after(last_order: str | None) -> str:
    if last_order is None:
        return "m"
    return f"{last_order}m"
