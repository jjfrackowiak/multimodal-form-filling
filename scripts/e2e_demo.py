"""Run the mixed-mode fleet fixture through the complete pipeline."""

# The demo is intentionally runnable without installing each workspace package.
# Ruff's E402 is expected after this path bootstrap.
# ruff: noqa: E402
from __future__ import annotations

import asyncio
import argparse
import io
import os
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
for source_root in (
    REPO_ROOT / "services" / "email-service" / "src",
    REPO_ROOT / "services" / "editor-service" / "src",
    REPO_ROOT / "packages" / "mff-contracts" / "src",
    REPO_ROOT / "packages" / "mff-fakes" / "src",
    REPO_ROOT / "packages" / "mff-docmodel" / "src",
    REPO_ROOT / "packages" / "mff-manifest" / "src",
    REPO_ROOT / "packages" / "mff-store" / "src",
    REPO_ROOT / "packages" / "mff-applier" / "src",
):
    sys.path.insert(0, str(source_root))

from google.adk.models.llm_response import LlmResponse
from google.genai import types

from editor_service.flows.derivative import review_derivative
from editor_service.flows.netnew import compose_netnew
from editor_service.llm.output import SliceTurnOutput
from editor_service.settings import Settings
from email_service.delivery import DeliveryDispatcher
from email_service.intake import ParsedRequest, parse_inbound, validate_intake
from email_service.orchestrator import OrchestratorDeps, run_request
from email_service.transport import Attachment, InboundMessage, InMemoryTransport, OutboundMessage
from mff_contracts import (
    Anchor,
    ClientInputs,
    Constraint,
    DerivativeArtifact,
    ImageAnalysis,
    JobImage,
    JobRecord,
    JobRequest,
    Manifest,
    Mode,
    NetNewArtifact,
    RequestRecord,
    RequestResult,
    Requirement,
    ReviewComment,
    SliceReport,
    SliceRequest,
)
from mff_fakes import FakeLlm
from mff_manifest import parse_manifest
from mff_store.memory import (
    InMemoryArtifactRepository,
    InMemoryBlobStore,
    InMemoryJobRepository,
    InMemoryRequestRepository,
)

FIXTURE_ROOT = REPO_ROOT / "fixtures" / "fleet-vehicle-return"
ZIP_CONTENT_TYPE = "application/zip"
DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@dataclass
class GoldenExtractor:
    """A deterministic stand-in for the manifest model extractor."""

    requirements: list[Requirement]
    _used: bool = field(default=False, init=False)

    async def extract(self, _chunk: str, *, offset: int) -> list[Requirement]:
        del offset
        if self._used:
            return []
        self._used = True
        return [
            requirement.model_copy(
                update={
                    "id": "R-00",
                    "ordinal": -1,
                    "source_line": -1,
                    "constraint": (
                        requirement.constraint.model_copy(update={"source_line": -1})
                        if requirement.constraint is not None
                        else None
                    ),
                }
            )
            for requirement in self.requirements
        ]


@dataclass(frozen=True)
class DemoRun:
    parsed: ParsedRequest
    intake_valid: bool
    manifest: Manifest
    result: RequestResult
    outbound: OutboundMessage
    jobs: list[JobRecord]
    flow_calls: list[SliceRequest]
    flow_reports: list[SliceReport]
    flow_runs: list[tuple[SliceRequest, SliceReport]]
    checker_output: str


def _fixture_requirements() -> list[Requirement]:
    data: dict[str, Any] = yaml.safe_load(
        (FIXTURE_ROOT / "expected_requirements.yaml").read_text(encoding="utf-8")
    )
    requirements: list[Requirement] = []
    for entry in data["requirements"]:
        raw_constraint = entry.get("constraint")
        constraint = None
        if raw_constraint is not None:
            constraint = Constraint(
                kind=raw_constraint["kind"],
                value=raw_constraint["value"],
                source_span=raw_constraint["constraint_source_span"],
                source_line=raw_constraint["constraint_source_line"],
                note=raw_constraint.get("note"),
            )
        requirements.append(
            Requirement(
                id=entry["id"],
                ordinal=entry["ordinal"],
                text=entry["text"],
                source_span=entry["source_span"],
                source_line=entry["source_line"],
                expected_count=entry.get("expected_count", 1),
                constraint=constraint,
                ambiguity=entry.get("ambiguity"),
            )
        )
    return requirements


def _fixture_comments() -> dict[str, ReviewComment]:
    data: dict[str, Any] = yaml.safe_load(
        (FIXTURE_ROOT / "expected_output" / "review.yaml").read_text(encoding="utf-8")
    )
    return {
        entry["requirement_id"]: ReviewComment(
            requirement_id=entry["requirement_id"],
            anchor=Anchor(kind="document"),
            verdict=entry["verdict"],
            justification=entry["justification"].strip(),
            suggestion=(entry.get("suggestion") or "").strip() or None,
        )
        for entry in data["verdicts"]
    }


def _fixture_email() -> InboundMessage:
    manifest = (FIXTURE_ROOT / "manifest.txt").read_text(encoding="utf-8")
    derivative_buffer = io.BytesIO()
    with zipfile.ZipFile(derivative_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        source = FIXTURE_ROOT / "input" / "derivative" / "form_supplied.docx"
        archive.write(source, arcname="form_supplied.docx")

    netnew_buffer = io.BytesIO()
    netnew_root = FIXTURE_ROOT / "input" / "netnew"
    with zipfile.ZipFile(netnew_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(netnew_root.rglob("*")):
            if path.is_file():
                archive.write(path, arcname=str(path.relative_to(netnew_root)))

    return InboundMessage(
        message_id="<b9-demo@example.test>",
        sender="client@example.test",
        subject="Zwrot pojazdu WN-7020U",
        body=manifest,
        received_at=datetime(2026, 8, 30, 12, 0, tzinfo=UTC),
        attachments=[
            Attachment(
                filename="derivative.zip",
                content_type=ZIP_CONTENT_TYPE,
                data=derivative_buffer.getvalue(),
            ),
            Attachment(
                filename="net-new.zip",
                content_type=ZIP_CONTENT_TYPE,
                data=netnew_buffer.getvalue(),
            ),
        ],
    )


async def _to_job_requests(
    parsed: ParsedRequest, requirements: list[Requirement], blob_store: InMemoryBlobStore
) -> list[JobRequest]:
    jobs: list[JobRequest] = []
    for index, parsed_job in enumerate(parsed.jobs, start=1):
        job_id = f"b9-job-{index}"
        if parsed_job.mode == Mode.DERIVATIVE:
            assert parsed_job.form is not None
            form = await blob_store.put(
                parsed_job.form.data, content_type=DOCX_CONTENT_TYPE, kind="source"
            )
            jobs.append(
                JobRequest(
                    job_id=job_id,
                    request_id=parsed.message_id,
                    mode=Mode.DERIVATIVE,
                    form_id=parsed_job.form_id,
                    form=form,
                    requirements=requirements,
                )
            )
            continue

        assert parsed_job.inputs is not None
        input_data = parsed_job.inputs
        images: list[JobImage] = []
        for image in input_data.images:
            blob = await blob_store.put(image.data, content_type=image.content_type, kind="input")
            images.append(
                JobImage(
                    blob=blob,
                    original_filename=image.filename,
                    source="attachment",
                )
            )
        jobs.append(
            JobRequest(
                job_id=job_id,
                request_id=parsed.message_id,
                mode=Mode.NET_NEW,
                form_id=parsed_job.form_id,
                inputs=ClientInputs(
                    set_id=input_data.inputs.set_id,
                    texts=input_data.inputs.texts,
                ),
                images=images,
                requirements=requirements,
            )
        )
    return jobs


@dataclass
class FlowSliceRunner:
    """B9's in-process bridge from the B5 protocol to the B6/B7 flows."""

    comments: dict[str, ReviewComment]
    inventory: list[ImageAnalysis]
    netnew_texts: dict[str, dict[str, str]]
    live_model: bool = False
    calls: list[SliceRequest] = field(default_factory=list)
    reports: list[SliceReport] = field(default_factory=list)
    runs: list[tuple[SliceRequest, SliceReport]] = field(default_factory=list)

    async def run(self, request: SliceRequest) -> SliceReport:
        self.calls.append(request)
        if request.mode is Mode.DERIVATIVE:
            assert isinstance(request.artifact, DerivativeArtifact)
            model = None
            if not self.live_model:
                comments = [self.comments[requirement.id] for requirement in request.requirements]
                model = FakeLlm.script([SliceTurnOutput(comments=comments)])
            report = await review_derivative(
                request,
                request.artifact,
                self.inventory,
                model=model,
            )
        else:
            assert isinstance(request.artifact, NetNewArtifact)
            model = None
            if not self.live_model:
                comments = [self.comments[requirement.id] for requirement in request.requirements]
                model = FakeLlm.script(
                    [_netnew_mutations(request), SliceTurnOutput(comments=comments)]
                )
            report = await compose_netnew(
                request,
                request.artifact,
                self.inventory,
                self.netnew_texts[request.job_id],
                model=model,
            )
        self.reports.append(report)
        self.runs.append((request, report))
        return report


def _netnew_mutations(request: SliceRequest) -> LlmResponse:
    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        name="append_entry",
                        args={
                            "section_id": "section-09",
                            "label": requirement.id,
                            "value": f"Reviewed client evidence for {requirement.id}",
                            "requirement_id": requirement.id,
                        },
                    )
                )
                for requirement in request.requirements
            ],
        )
    )


def _fixture_inventory() -> list[ImageAnalysis]:
    data: dict[str, Any] = yaml.safe_load((FIXTURE_ROOT / "inventory.yaml").read_text("utf-8"))
    return [ImageAnalysis.model_validate(image) for image in data["images"]]


async def run_demo(*, live_model: bool = False) -> DemoRun:
    """Run offline by default; use real Gemini calls only when explicitly requested."""
    if live_model:
        Settings.from_env()
    transport = InMemoryTransport()
    inbound = _fixture_email()
    transport.deliver(inbound)
    unseen = await transport.fetch_unseen()
    assert unseen == [inbound]

    parsed = parse_inbound(unseen[0])
    intake = validate_intake(
        parsed,
        allowed_senders=frozenset({"client@example.test"}),
        now=inbound.received_at,
    )
    assert intake.valid, intake.problems
    assert len(parsed.jobs) == 2

    requirements = _fixture_requirements()
    manifest = await parse_manifest(
        parsed.manifest_raw,
        extractor=GoldenExtractor(requirements),
    )
    assert [requirement.id for requirement in manifest.requirements] == [
        f"R-{index:02d}" for index in range(1, 11)
    ]

    blob_store = InMemoryBlobStore()
    jobs = await _to_job_requests(parsed, manifest.requirements, blob_store)
    request = RequestRecord(
        request_id=parsed.message_id,
        manifest_raw=parsed.manifest_raw,
        requirements=manifest.requirements,
        job_ids=[job.job_id for job in jobs],
        reply_to=parsed.sender,
        original_message_id=parsed.message_id,
        status="running",
    )
    request_repo = InMemoryRequestRepository()
    job_repo = InMemoryJobRepository()
    await request_repo.put(request)
    runner = FlowSliceRunner(
        comments=_fixture_comments(),
        inventory=_fixture_inventory(),
        netnew_texts={
            job.job_id: dict(job.inputs.texts)
            for job in jobs
            if job.mode is Mode.NET_NEW and job.inputs is not None
        },
        live_model=live_model,
    )
    deps = OrchestratorDeps(
        artifact_repo=InMemoryArtifactRepository(),
        job_repo=job_repo,
        blob_store=blob_store,
        runner=runner,
    )
    result = await run_request(request, jobs, deps)
    assert result.status == "done"
    records = await job_repo.for_request(request.request_id)
    assert len(records) == 2
    assert all(record.status == "done" for record in records)

    dispatcher = DeliveryDispatcher(
        requests=request_repo,
        transport=transport,
        blobs=blob_store,
    )
    outbound = await dispatcher.on_jobs_settled(
        result,
        request,
        comments=list(_fixture_comments().values()),
        jobs=records,
    )
    assert outbound is not None
    assert {attachment.filename for attachment in outbound.attachments} == {
        "form_supplied.docx",
        "WN-7020U.docx",
        "parsed-requirements.docx",
    }
    assert all(requirement.text not in outbound.body for requirement in manifest.requirements)
    assert len(transport.sent) == 1

    derivative = next(record for record in records if record.form_id.endswith(".docx"))
    assert derivative.document is not None
    checker = FIXTURE_ROOT / "check_output.py"
    with tempfile.TemporaryDirectory(prefix="mff-b9-") as directory:
        output = Path(directory) / "report_reviewed.docx"
        output.write_bytes(await blob_store.get(derivative.document))
        checked = subprocess.run(
            [sys.executable, str(checker), str(output)],
            cwd=REPO_ROOT,
            capture_output=True,
            check=False,
            text=True,
        )
    checker_output = checked.stdout.strip()
    if checked.returncode != 0:
        raise RuntimeError(f"fixture checker failed:\n{checker_output}\n{checked.stderr}")

    return DemoRun(
        parsed=parsed,
        intake_valid=intake.valid,
        manifest=manifest,
        result=result,
        outbound=outbound,
        jobs=records,
        flow_calls=runner.calls,
        flow_reports=runner.reports,
        flow_runs=runner.runs,
        checker_output=checker_output,
    )


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Run the fleet form-filling E2E demo.")
    parser.add_argument(
        "--live",
        action="store_true",
        help="use the configured Gemini model through ADC instead of FakeLlm",
    )
    args = parser.parse_args()
    if args.live and not os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip():
        parser.error("--live requires GOOGLE_CLOUD_PROJECT and Application Default Credentials")

    run = await run_demo(live_model=args.live)
    print(f"B9 {'live ' if args.live else ''}e2e demo: PASS")
    print(f"RequestResult status: {run.result.status}")
    print(f"jobs done: {len(run.jobs)}; attachments: {len(run.outbound.attachments)}")
    print("requirements: " + ", ".join(requirement.id for requirement in run.manifest.requirements))
    print(run.checker_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
