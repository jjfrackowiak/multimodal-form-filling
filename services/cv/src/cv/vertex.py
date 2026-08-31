from __future__ import annotations

import logging
import os
import random
import re
import threading
import time
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

log = logging.getLogger("cv")

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "linen-badge-507111-r6")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
MODEL = os.environ.get("CV_MODEL", "gemini-2.5-flash")

# Live mixed-mode still 429'd with 1 worker: the next photo (and the next job)
# starts as soon as generateContent returns. ~15 calls/min on this quota.
_RETRY_IN_S = re.compile(r"retry in ([\d.]+)\s*s", re.I)
_RETRY_DELAY_FIELD = re.compile(r"retryDelay['\"]\s*[:=]\s*['\"](\d+(?:\.\d+)?)s", re.I)
_GATE = threading.Lock()
_next_ok = 0.0


def client() -> genai.Client:
    return genai.Client(vertexai=True, project=PROJECT, location=LOCATION)


def _min_interval() -> float:
    return max(0.0, float(os.environ.get("CV_VERTEX_MIN_INTERVAL_SECONDS", "8")))


def _retry_wait(exc: Exception, attempt: int) -> float:
    text = str(exc)
    hinted = 0.0
    match = _RETRY_IN_S.search(text) or _RETRY_DELAY_FIELD.search(text)
    if match:
        hinted = float(match.group(1))
    backoff = min(2**attempt, 32) + random.uniform(0, 1)
    return max(hinted, backoff, 8.0)


def _pace() -> None:
    global _next_ok
    wait = _next_ok - time.monotonic()
    if wait > 0:
        log.info("vertex pacing sleep %.1fs", wait)
        time.sleep(wait)


def _booked() -> None:
    global _next_ok
    _next_ok = time.monotonic() + _min_interval()


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
        with _GATE:
            _pace()
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
                _booked()
            except Exception as e:
                last = e
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    delay = _retry_wait(e, attempt)
                    log.info("vertex 429 attempt %s sleeping %.1fs", attempt + 1, delay)
                    time.sleep(delay)
                    _booked()
                    continue
                raise
        parsed = response.parsed
        if isinstance(parsed, schema):
            return parsed
        if parsed is not None:
            return schema.model_validate(parsed)
        return schema.model_validate_json(response.text or "{}")
    raise last or RuntimeError("vertex failed")
