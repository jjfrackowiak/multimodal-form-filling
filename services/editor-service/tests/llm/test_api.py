"""Brief DoD 6, 7: `POST /slices:run` round-trips a real `SliceRequest`, and `/healthz`
never constructs a model client."""

from __future__ import annotations

import pytest
from golden import GOLDEN_REQUIREMENTS, golden_slice_request, make_comment
from google.adk.agents import LlmAgent
from starlette.testclient import TestClient

from editor_service.api.deps import get_slice_runner
from editor_service.llm.deps import EditorDeps
from editor_service.llm.output import SliceTurnOutput
from editor_service.llm.run import run_slice
from editor_service.main import create_app
from mff_contracts import SliceReport, SliceRequest
from mff_fakes import FakeLlm


def test_healthz_does_not_require_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """No GOOGLE_CLOUD_PROJECT set at all — /healthz must still answer 200, proving it
    never resolves settings or constructs a model client."""
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

    client = TestClient(create_app())
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_imports_nothing_from_llm_or_settings() -> None:
    """Static guarantee to back the runtime one above: the health router's own source
    names neither `editor_service.llm` nor `editor_service.settings`."""
    import inspect

    from editor_service.api.routers import health

    source = inspect.getsource(health)
    assert "editor_service.llm" not in source
    assert "editor_service.settings" not in source


def test_wired_runner_without_a_model_project_fails_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No images → skip CV; missing GOOGLE_CLOUD_PROJECT fails at agent construction."""
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("CV_URL", raising=False)
    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.post("/slices:run", json=golden_slice_request().model_dump(mode="json"))
    assert response.status_code == 400


def test_slices_run_round_trips_a_real_slice_request_from_the_fixture() -> None:
    """Overrides `get_slice_runner` with a `FakeLlm`-backed runner — the same pattern
    `HttpVisionTool` tests use for the CV client —
    and posts a real `SliceRequest` built from the fixture's first six requirements."""
    turn_output = SliceTurnOutput(comments=[make_comment(r.id) for r in GOLDEN_REQUIREMENTS])
    fake = FakeLlm.script([turn_output])
    agent = LlmAgent(
        name="reviewer", model=fake, instruction="x", output_schema=SliceTurnOutput, tools=[]
    )

    async def fake_runner(req: SliceRequest) -> SliceReport:
        deps = EditorDeps(artifact=req.artifact, agent=agent)
        return await run_slice(req, deps)

    app = create_app()
    app.dependency_overrides[get_slice_runner] = lambda: fake_runner
    client = TestClient(app)

    request_body = golden_slice_request()
    response = client.post("/slices:run", json=request_body.model_dump(mode="json"))

    assert response.status_code == 200
    report = SliceReport.model_validate(response.json())
    assert report.slice_id == request_body.slice_id
    assert report.attempts_used == 1
    assert report.unverified == []
    assert {c.requirement_id for c in report.comments} == {r.id for r in GOLDEN_REQUIREMENTS}
