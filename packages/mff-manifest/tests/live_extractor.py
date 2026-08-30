"""A minimal, real `RequirementExtractor` — for the live eval only.

Not the production implementation: that lives in the editor service (B8's territory) as
an ADK agent. This is the smallest thing shaped the same way and is exactly what "a real
extractor prompts for JSON and validates the result" (see the brief) means in practice —
Gemma has no native structured-output mode, so this asks in plain language and parses
what comes back, rather than relying on a `response_schema`.

Imported only from inside `test_live_eval.py`'s gated test body, so `google.genai` is
never touched by an ordinary `make check` run. Lives entirely under `tests/`, never under
`src/mff_manifest` — see `test_import_boundary.py`. Needs the `live-eval` extra:
`uv sync --extra live-eval` (declared in mff-manifest's own `pyproject.toml`, never a
default or runtime dependency).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import google.genai as genai

from mff_contracts import Constraint, Requirement

__all__ = ["GemmaJsonExtractor"]

_INSTRUCTIONS = """\
You are extracting REQUIREMENTS from a client's free-text manifest describing what a \
vehicle-return photo/document form must contain. The text is real client writing and may \
contain typos and missing diacritics — copy it exactly; never correct spelling or wording.

Return ONLY a JSON object of this shape, no markdown fences, no commentary:
{"requirements": [
  {
    "text": "one normalised, individually-checkable English sentence describing what is required",
    "source_span": "the EXACT verbatim substring of the input text this requirement comes from",
    "expected_count": 1,
    "constraint": {"kind": "...", "value": "...", "source_span": "...", "note": "..."},
    "ambiguity": "a short machine-readable tag, or omit the field if there is none"
  }
]}

Rules:
- source_span must be copied character-for-character from the input text, typos included.
  It is never invented, never translated, never corrected.
- A count like "4x seats" is ONE requirement with expected_count 4, never four requirements.
- One sentence can name two separately checkable things (for example a windscreen shot
  "from inside and outside") — emit two requirements, each anchored to the same source_span.
- A constraint stated elsewhere in the text can qualify an item named earlier or later in
  the text. If you can identify which requirement it qualifies, attach it there via the
  "constraint" field (omit "constraint" entirely on every other requirement).
- If the same real-world item seems to be named twice in different words and you cannot
  tell whether that means two distinct instances or one item described twice, keep it as
  ONE requirement, fold the repetition into expected_count, and set "ambiguity" to a short
  tag explaining the situation. Never invent a requirement that is not named anywhere in
  the text — recall may fall short, but precision must stay 1.0.
"""

_FENCE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


def _extract_json_object(text: str) -> dict[str, Any]:
    """The validation half of "prompt for JSON and validate the result": strip a stray
    code fence if the model added one anyway, then parse. A malformed response raises
    here (`json.JSONDecodeError`, `KeyError`) — that is this extractor's own failure to
    surface, not something `parse_manifest` should paper over."""
    fenced = _FENCE.search(text)
    payload = fenced.group(1) if fenced else text
    result: dict[str, Any] = json.loads(payload)
    return result


@dataclass
class GemmaJsonExtractor:
    """Calls Gemma once per chunk, asks for JSON, parses it into `Requirement`s.

    Sets placeholder `id`/`ordinal`/`source_line` — `parse_manifest` recomputes all three
    from `source_span`, so this extractor only has to get right the fields it actually
    controls: `text`, `source_span`, `expected_count`, `constraint`, `ambiguity`.
    """

    model_id: str
    api_key: str
    last_usage: dict[str, int] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self._client = genai.Client(api_key=self.api_key)

    async def extract(self, chunk: str, *, offset: int) -> list[Requirement]:
        response = await self._client.aio.models.generate_content(
            model=self.model_id,
            contents=f"{_INSTRUCTIONS}\nINPUT TEXT:\n{chunk}",
        )
        usage = response.usage_metadata
        if usage is not None:
            self.last_usage = {
                "prompt_tokens": usage.prompt_token_count or 0,
                "response_tokens": usage.candidates_token_count or 0,
                "total_tokens": usage.total_token_count or 0,
            }
        text = response.text
        if not text:
            raise ValueError(f"empty response from {self.model_id}")
        data = _extract_json_object(text)
        return [self._to_requirement(item) for item in data["requirements"]]

    @staticmethod
    def _to_requirement(item: dict[str, Any]) -> Requirement:
        constraint = None
        raw_constraint = item.get("constraint")
        if raw_constraint:
            constraint = Constraint(
                kind=raw_constraint["kind"],
                value=raw_constraint["value"],
                source_span=raw_constraint["source_span"],
                source_line=0,  # parse_manifest recomputes this from source_span
                note=raw_constraint.get("note"),
            )
        return Requirement(
            id="R-00",  # parse_manifest overwrites this after the canonical sort
            ordinal=0,  # parse_manifest recomputes this from source_span
            source_line=0,  # parse_manifest recomputes this from source_span
            text=item["text"],
            source_span=item["source_span"],
            expected_count=item.get("expected_count", 1),
            constraint=constraint,
            ambiguity=item.get("ambiguity"),
        )
