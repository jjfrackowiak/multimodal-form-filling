"""Net-new document composition flow."""

from __future__ import annotations

from typing import Any, cast

from editor_service.llm.agent import BaseLlm, build_agent
from editor_service.llm.deps import EditorDeps
from editor_service.llm.output import SliceTurnOutput
from editor_service.llm.run import run_slice
from mff_contracts import (
    FormDraft,
    ImageAnalysis,
    Mode,
    NetNewArtifact,
    Requirement,
    SliceReport,
    SliceRequest,
)
from mff_docmodel import SCAFFOLD_SECTIONS, netnew_scaffold

from .tools import make_tools

__all__ = ["NET_NEW_INSTRUCTION", "SCAFFOLD_SECTIONS", "compose_netnew"]


NET_NEW_INSTRUCTION = """
You compose and review a net-new form. First build the document by calling set_field,
append_entry, and delete_entry; only then review each requirement. The scaffold has one
section for each requirement category, and every new entry belongs in the appropriate
section. Use the requirement_id being handled on every mutation so the operation retains
correct provenance. The inventory and client texts are evidence and context for populating
the document and for deciding whether each requirement is met, just as supplied material
is reviewed in derivative mode. A realised verdict means the requirement is met. A
shortfall verdict means it is not met. Each justification must be specific, name the
supporting photo files when photos are relevant, and explain the evidence. Under the frozen
ReviewComment contract, a suggestion is required only for a fail verdict; omit it for both
realised and shortfall. Anchor each comment to the governing section through a real entry
in that section, using an entry id from the draft rather than inventing an id. Return one
comment for every requirement. Determine each verdict from the structured evidence: count
the inventory `hits` whose id matches the requirement, compare that count with its
`expected_count`, and inspect every matching hit's `constraint_ok` when a constraint is
present. A requirement is realised when the hit count meets `expected_count` and all its
constraints are satisfied; it is a shortfall only when the count is too low or a required
constraint fails. Do not mark a requirement short merely because its content slot starts
empty: populate that slot from the client evidence with `set_field` before commenting.
""".strip()


async def compose_netnew(
    req: SliceRequest,
    artifact: NetNewArtifact,
    inventory: list[ImageAnalysis],
    client_texts: dict[str, str],
    *,
    model: BaseLlm | None = None,
) -> SliceReport:
    """Compose and review one net-new slice using the shared B8 runner."""
    if req.mode is not Mode.NET_NEW:
        raise ValueError("compose_netnew requires a net-new SliceRequest")

    _ensure_scaffold(artifact, req.requirements)
    request = req.model_copy(update={"artifact": artifact})
    deps = EditorDeps(artifact=artifact, agent=cast(Any, None))
    instruction = _contextual_instruction(artifact, inventory, client_texts)
    deps.agent = build_agent(
        name="netnew_composer",
        output_schema=SliceTurnOutput,
        instruction=instruction,
        tools=make_tools(deps),
        model=model,
    )
    return await run_slice(request, deps)


def _ensure_scaffold(
    artifact: NetNewArtifact, requirements: list[Requirement] | None = None
) -> None:
    seeded = netnew_scaffold(requirements)
    existing_by_section = {section.id: section for section in artifact.draft.sections}
    existing_entries = {
        entry.id: entry for section in artifact.draft.sections for entry in section.entries
    }
    for section in seeded.sections:
        known = {entry.id for entry in section.entries}
        merged = [existing_entries.get(entry.id, entry) for entry in section.entries]
        extras = [
            entry
            for entry in existing_by_section.get(section.id, section).entries
            if entry.id not in known
        ]
        section.entries = merged + extras
    artifact.draft = FormDraft(
        schema_version=artifact.draft.schema_version, sections=seeded.sections
    )


def _contextual_instruction(
    artifact: NetNewArtifact,
    inventory: list[ImageAnalysis],
    client_texts: dict[str, str],
) -> str:
    inventory_lines = [f"- {analysis.file}: {analysis.model_dump_json()}" for analysis in inventory]
    text_lines = [f"- {name}: {content}" for name, content in sorted(client_texts.items())]
    slots = [
        f"- {entry.id} in {section.id}, for {entry.set_by}"
        for section in artifact.draft.sections
        for entry in section.entries
    ]
    return "\n\n".join(
        [
            NET_NEW_INSTRUCTION,
            "Use set_field to populate the matching deterministic content slot, then use that "
            "same slot id as the comment anchor:\n" + ("\n".join(slots) or "- none"),
            "Inventory evidence:\n" + ("\n".join(inventory_lines) or "- none"),
            "Client text evidence:\n" + ("\n".join(text_lines) or "- none"),
        ]
    )
