"""The retry loop — the design decision most likely to be got wrong (B8 brief).

`run_slice` owns the whole retry lifecycle: run the agent, validate completeness on Python
objects, retry with the agent's own previous output and the error in front of it (same ADK
session, next user turn — never a hand-built message history), and after three attempts
mark the stragglers `unverified` and return *normally*. No ADK or provider exception may
ever escape to the orchestrator: `SliceRequest` carries no `pending`, no `history` and no
`validator_error`, because a `SliceReport` is always well-formed by the time it leaves here.
"""

from __future__ import annotations

from google.adk.apps import App
from google.adk.runners import Runner
from google.genai import types
from pydantic import ValidationError

from editor_service.llm.deps import EditorDeps
from editor_service.llm.output import SliceTurnOutput
from editor_service.llm.plugins import UsagePlugin
from editor_service.llm.prompts import initial_prompt, retry_prompt
from editor_service.llm.validate import validate
from mff_contracts import ReviewComment, SliceReport, SliceRequest

__all__ = ["MAX_ATTEMPTS", "run_slice"]

APP_NAME = "editor_service"

# Three attempts: one clean run plus two chances to self-correct against the validator's
# own error before the stragglers are marked `unverified` and the report returns normally
# (req 17 — see the brief). Not configurable per-request: `SliceRequest` carries no such
# field, on purpose — see mff_contracts.slices.
MAX_ATTEMPTS = 3


async def run_slice(req: SliceRequest, deps: EditorDeps) -> SliceReport:
    """Run one slice to a well-formed `SliceReport`. Never raises.

    `deps.agent` must already be built (by `llm.agent.build_agent`, in B6/B7) with an
    `output_schema` of `SliceTurnOutput` — this function only runs it, it does not build
    it. `deps.artifact` is read (never mutated) by the completeness validator; any mutation
    happens through tools B6/B7 register on the agent, which append to `deps.op_log`
    directly and are copied into the report verbatim.
    """
    usage_plugin = deps.usage_plugin or UsagePlugin(budget=deps.token_budget)
    deps.usage_plugin = usage_plugin

    session_service = deps.session_service
    await session_service.create_session(
        app_name=APP_NAME,
        user_id=req.job_id,
        session_id=req.slice_id,
        state={
            "slice_id": req.slice_id,
            "mode": req.mode.value,
            "requirement_count": len(req.requirements),
        },
    )

    app = App(name=APP_NAME, root_agent=deps.agent, plugins=[usage_plugin])
    runner = Runner(app=app, session_service=session_service)

    settled: dict[str, ReviewComment] = {}
    pending = [requirement.id for requirement in req.requirements]
    message = initial_prompt(req)
    attempt = 0

    for attempt in range(1, MAX_ATTEMPTS + 1):
        output, turn_error = await _one_turn(runner, req, message)

        if output is None:
            errors = dict.fromkeys(pending, turn_error or "the turn produced no usable output")
        else:
            passed, errors = validate(output, pending, deps.artifact)
            settled.update(passed)  # rule 2: an id already in `settled` is never in `pending`
            # again below, so a later `passed` for the same id can never reach here.

        pending = [requirement_id for requirement_id in pending if requirement_id not in settled]
        if not pending:
            break
        message = retry_prompt(pending, errors)

    return SliceReport(
        slice_id=req.slice_id,
        comments=list(settled.values()),
        ops=list(deps.op_log),
        unverified=pending,
        attempts_used=attempt,
    )


async def _one_turn(
    runner: Runner, req: SliceRequest, message: str
) -> tuple[SliceTurnOutput | None, str | None]:
    """Run one ADK turn and parse its final response as `SliceTurnOutput`.

    Returns `(output, None)` on success or `(None, reason)` on any failure — a model/
    transport error, a script exhaustion in tests, an empty response, or output that does
    not validate against the schema. Every failure is caught here: this is the run
    boundary the brief means by "catch ... and convert."
    """
    content = types.Content(role="user", parts=[types.Part(text=message)])
    try:
        final_event = None
        async for event in runner.run_async(
            user_id=req.job_id, session_id=req.slice_id, new_message=content
        ):
            final_event = event
    except Exception as exc:  # noqa: BLE001 - the run boundary; nothing may escape it
        return None, f"{type(exc).__name__}: {exc}"

    if final_event is None or final_event.content is None or not final_event.content.parts:
        return None, "the model turn produced no content"

    text = "".join(part.text or "" for part in final_event.content.parts)
    if not text.strip():
        error_message = final_event.error_message or "the model turn returned empty text"
        return None, error_message

    try:
        return SliceTurnOutput.model_validate_json(text), None
    except ValidationError as exc:
        return None, f"output did not match the expected schema: {exc}"
