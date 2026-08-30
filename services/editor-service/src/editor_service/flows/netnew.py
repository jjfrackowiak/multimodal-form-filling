"""Net-new document composition flow."""

from __future__ import annotations

from typing import Any, cast

from google.adk.models.base_llm import BaseLlm

from editor_service.llm.agent import build_agent
from editor_service.llm.deps import EditorDeps
from editor_service.llm.output import SliceTurnOutput
from editor_service.llm.run import run_slice
from mff_contracts import (
    FormDraft,
    ImageAnalysis,
    Mode,
    NetNewArtifact,
    Section,
    SliceReport,
    SliceRequest,
)

from .tools import make_tools

__all__ = ["NET_NEW_INSTRUCTION", "compose_netnew"]


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
comment for every requirement.
""".strip()

SCAFFOLD_SECTIONS: tuple[tuple[str, str], ...] = (
    ("section-01", "1. Pod maską"),
    ("section-02", "2. Fotele"),
    ("section-03", "3. Przekątne pojazdu"),
    ("section-04", "4. Podsufitka"),
    ("section-05", "5. Przednia szyba"),
    ("section-06", "6. Bieżnik opony"),
    ("section-07", "7. Bagażnik i wyposażenie"),
    ("section-08", "8. Zegary"),
    ("section-09", "9. Uwagi"),
)


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

    _ensure_scaffold(artifact)
    request = req.model_copy(update={"artifact": artifact})
    deps = EditorDeps(artifact=artifact, agent=cast(Any, None))
    instruction = _contextual_instruction(inventory, client_texts)
    deps.agent = build_agent(
        name="netnew_composer",
        output_schema=SliceTurnOutput,
        instruction=instruction,
        tools=make_tools(deps),
        model=model,
    )
    return await run_slice(request, deps)


def _ensure_scaffold(artifact: NetNewArtifact) -> None:
    existing = {section.id: section for section in artifact.draft.sections}
    artifact.draft = FormDraft(
        schema_version=artifact.draft.schema_version,
        sections=[
            _scaffold_section(existing.get(section_id), section_id, title)
            for section_id, title in SCAFFOLD_SECTIONS
        ],
    )


def _scaffold_section(section: Section | None, section_id: str, title: str) -> Section:
    if section is None:
        return Section(id=section_id, title=title)
    return section.model_copy(update={"title": title})


def _contextual_instruction(inventory: list[ImageAnalysis], client_texts: dict[str, str]) -> str:
    inventory_lines = [f"- {analysis.file}: {analysis.model_dump_json()}" for analysis in inventory]
    text_lines = [f"- {name}: {content}" for name, content in sorted(client_texts.items())]
    return "\n\n".join(
        [
            NET_NEW_INSTRUCTION,
            "Inventory evidence:\n" + ("\n".join(inventory_lines) or "- none"),
            "Client text evidence:\n" + ("\n".join(text_lines) or "- none"),
        ]
    )
