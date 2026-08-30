from __future__ import annotations

import os
import time
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "linen-badge-507111-r6")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
MODEL = os.environ.get("CV_MODEL", "gemini-3.7-flash")


def client() -> genai.Client:
    return genai.Client(vertexai=True, project=PROJECT, location=LOCATION)


def generate_structured(
    c: genai.Client,
    *,
    jpeg: bytes,
    prompt: str,
    schema: type[T],
    retries: int = 6,
) -> T:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            response = c.models.generate_content(
                model=MODEL,
                contents=[
                    types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"),
                    prompt,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        disable=True
                    ),
                ),
            )
            parsed = response.parsed
            if isinstance(parsed, schema):
                return parsed
            if parsed is not None:
                return schema.model_validate(parsed)
            return schema.model_validate_json(response.text or "{}")
        except Exception as e:
            last = e
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                time.sleep(min(8 * (attempt + 1), 40))
                continue
            raise
    raise last or RuntimeError("vertex failed")
