from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from cv import vertex


class _Label(BaseModel):
    note: str = "ok"


class _Models:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    def generate_content(self, **kwargs: object) -> object:
        self.calls += 1
        item = self.outcomes.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def _reset_pace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CV_VERTEX_MIN_INTERVAL_SECONDS", "8")
    vertex._next_ok = 0.0


def test_retry_wait_honors_please_retry_in() -> None:
    exc = RuntimeError("429 RESOURCE_EXHAUSTED. Please retry in 13.5s.")
    assert vertex._retry_wait(exc, attempt=0) >= 13.5


def test_429_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(vertex.time, "sleep", sleeps.append)
    monkeypatch.setattr(vertex.time, "monotonic", lambda: 1000.0)
    parsed = _Label(note="ok")
    models = _Models(
        [
            RuntimeError("429 RESOURCE_EXHAUSTED. Please retry in 9s."),
            SimpleNamespace(parsed=parsed, text="{}"),
        ]
    )
    out = vertex.generate_structured(
        SimpleNamespace(models=models),  # type: ignore[arg-type]
        jpeg=b"\xff\xd8\xff",
        prompt="x",
        schema=_Label,
    )
    assert out.note == "ok"
    assert models.calls == 2
    assert sleeps[0] >= 9.0


def test_paces_between_successes(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    now = {"t": 0.0}

    def monotonic() -> float:
        return now["t"]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now["t"] += seconds

    monkeypatch.setattr(vertex.time, "sleep", sleep)
    monkeypatch.setattr(vertex.time, "monotonic", monotonic)
    parsed = _Label(note="ok")
    models = _Models(
        [
            SimpleNamespace(parsed=parsed, text="{}"),
            SimpleNamespace(parsed=parsed, text="{}"),
        ]
    )
    client = SimpleNamespace(models=models)
    vertex.generate_structured(client, jpeg=b"\xff\xd8\xff", prompt="x", schema=_Label)  # type: ignore[arg-type]
    vertex.generate_structured(client, jpeg=b"\xff\xd8\xff", prompt="x", schema=_Label)  # type: ignore[arg-type]
    assert models.calls == 2
    assert sleeps and sleeps[0] >= 8.0
