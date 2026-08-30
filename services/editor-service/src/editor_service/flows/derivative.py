"""Review a supplied form without changing its document body."""

from __future__ import annotations

import json

from editor_service.llm import EditorDeps, SliceTurnOutput, build_agent, run_slice
from editor_service.llm.agent import BaseLlm
from mff_contracts import DerivativeArtifact, ImageAnalysis, Mode, SliceReport, SliceRequest

__all__ = ["DERIVATIVE_INSTRUCTION", "review_derivative"]

DERIVATIVE_INSTRUCTION = """
You are the derivative-form reviewer. Review the supplied document against the parsed
requirements and the pre-built image inventory. The verdict vocabulary is exactly `pass`
when a requirement is met and `fail` when it is not met. For a photo requirement,
`satisfied` means both the required count and every stated constraint are met; meeting the
count alone is not sufficient. In particular, R-04 can have two headliner photos and still
fail when one is not photographed from between the front seats. A justification must name
the specific photo filenames and explain why they satisfy or fail the requirement; never
make only a bare assertion. A `suggestion` is required for `fail` and must be omitted for
`pass`. Each comment must be anchored to the governing section heading. In this contract a
section is a heading `Node`, so use `anchor.kind="node"` and set `anchor.target_id` to that
heading Node's id. Use `anchor.kind="document"` only when no matching section exists.
The inventory is a list of `ImageAnalysis` records. Each record names a photo in `file` and
lists the requirement ids it covers in `hits`. Read `constraint_ok` and
`constraint_evidence` on the matching hit when a constraint matters. The inventory is
already analysed: do not re-analyse photos or invent evidence. Return one well-formed
comment per requirement in the slice. Derivative mode is read-only: do not emit any
`DraftOp` and do not alter the supplied document nodes.
""".strip()


def _instruction_with_context(artifact: DerivativeArtifact, inventory: list[ImageAnalysis]) -> str:
    nodes_json = json.dumps(
        [node.model_dump(mode="json") for node in artifact.nodes],
        indent=2,
        sort_keys=True,
    )
    inventory_json = json.dumps(
        [image.model_dump(mode="json") for image in inventory],
        indent=2,
        sort_keys=True,
    )
    return (
        f"{DERIVATIVE_INSTRUCTION}\n\n"
        f"Supplied document nodes (read-only JSON):\n{nodes_json}\n\n"
        f"Pre-built image inventory (JSON):\n{inventory_json}"
    )


async def review_derivative(
    req: SliceRequest,
    artifact: DerivativeArtifact,
    inventory: list[ImageAnalysis],
    *,
    model: BaseLlm | None = None,
) -> SliceReport:
    """Review one derivative slice using the shared ADK runner."""
    if req.mode is not Mode.DERIVATIVE:
        raise ValueError("review_derivative requires a derivative SliceRequest")

    request = req.model_copy(update={"artifact": artifact})
    agent = build_agent(
        name="derivative_reviewer",
        output_schema=SliceTurnOutput,
        instruction=_instruction_with_context(artifact, inventory),
        tools=[],
        model=model,
    )
    deps = EditorDeps(artifact=artifact, agent=agent)
    return await run_slice(request, deps)
