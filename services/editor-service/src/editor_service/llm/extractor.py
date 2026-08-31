"""RequirementExtractor that calls the parser model over Vertex ADC.

Lives in `llm/` so it is the one place allowed to import `google.genai`. The HTTP
router only sees `parse_manifest` + this class.
"""

from __future__ import annotations

import json
import re
from typing import Any

from google import genai

from editor_service.settings import get_settings
from mff_contracts import Constraint, Requirement

__all__ = ["VertexJsonExtractor"]

_INSTRUCTIONS = """\
You are extracting REQUIREMENTS from a client's free-text manifest describing what a \
vehicle-return photo/document form must contain. The text is real client writing and may \
contain typos — copy it exactly; never correct spelling or wording.

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
- A count like "4x seats" is ONE requirement with expected_count 4, never four requirements.
- One sentence can name two separately checkable things (for example a windscreen shot
  "from inside and outside") — emit two requirements, each anchored to the same source_span.
- A constraint stated elsewhere in the text can qualify an item named earlier or later.
  Attach it via "constraint"; omit the field on every other requirement.
- A line that only states a total number of photos ("16 photos", "16 zdjęć") is NOT a
  requirement. It is a checksum for the items below. Do not emit it.
- If the same verbatim phrase appears more than once (for example "Under the bonnet" on
  two lines), that is ONE requirement. Set expected_count to the number of mentions and
  set ambiguity to "repeated_verbatim_in_manifest". Do not emit two requirements.
- Never invent a requirement that is not named as a photographic or documentary item in
  the text — recall may fall short, but precision must stay 1.0.
"""

_FENCE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


def _extract_json_object(text: str) -> dict[str, Any]:
    fenced = _FENCE.search(text)
    payload = fenced.group(1) if fenced else text
    result: dict[str, Any] = json.loads(payload)
    return result


class VertexJsonExtractor:
    def __init__(self) -> None:
        settings = get_settings()
        self._model_id = settings.parser_model_id
        self._client = genai.Client(
            vertexai=True,
            project=settings.google_cloud_project,
            location=settings.google_cloud_location,
        )

    async def extract(self, chunk: str, *, offset: int) -> list[Requirement]:
        del offset
        response = await self._client.aio.models.generate_content(
            model=self._model_id,
            contents=f"{_INSTRUCTIONS}\nINPUT TEXT:\n{chunk}",
        )
        text = response.text
        if not text:
            raise ValueError(f"empty response from {self._model_id}")
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
                source_line=0,
                note=raw_constraint.get("note"),
            )
        return Requirement(
            id="R-00",
            ordinal=0,
            source_line=0,
            text=item["text"],
            source_span=item["source_span"],
            expected_count=item.get("expected_count", 1),
            constraint=constraint,
            ambiguity=item.get("ambiguity"),
        )
