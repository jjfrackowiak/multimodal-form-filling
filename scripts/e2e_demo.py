"""Run the offline mixed-mode fleet fixture through the complete pipeline."""

# The demo is intentionally runnable without installing each workspace package.
# Ruff's E402 is expected after this path bootstrap.
# ruff: noqa: E402
from __future__ import annotations

import asyncio
import importlib.util
import io
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
for source_root in (
    REPO_ROOT / "services" / "email-service" / "src",
    REPO_ROOT / "packages" / "mff-contracts" / "src",
    REPO_ROOT / "packages" / "mff-docmodel" / "src",
    REPO_ROOT / "packages" / "mff-manifest" / "src",
    REPO_ROOT / "packages" / "mff-store" / "src",
    REPO_ROOT / "packages" / "mff-applier" / "src",
):
    sys.path.insert(0, str(source_root))

from email_service.delivery import DeliveryDispatcher
from email_service.intake import ParsedRequest, parse_inbound, validate_intake
from email_service.orchestrator import OrchestratorDeps, run_request
from email_service.runner.fake import FakeSliceRunner
from email_service.transport import Attachment, InboundMessage, InMemoryTransport, OutboundMessage
from mff_contracts import (
    Anchor,
    ClientInputs,
    Constraint,
    DraftOp,
    JobImage,
    JobRecord,
    JobRequest,
    Manifest,
    Mode,
    RequestRecord,
    RequestResult,
    Requirement,
    ReviewComment,
    SliceReport,
    SliceRequest,
)
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


def _runner(comments: dict[str, ReviewComment]) -> FakeSliceRunner:
    """Build the current-main runner until the B6/B7 flow adapter is merged.

    B6/B7 are separate branches and their flow functions require editor-side inventory
    and session dependencies that the B5 `SliceRunner` protocol does not carry. Once
    both flows land, replace this fallback with a runner that passes a
    `FakeLlm.script(...)` to each flow and translates the flow's `SliceReport` directly.
    """
    try:
        flows_available = all(
            importlib.util.find_spec(module_name) is not None
            for module_name in (
                "editor_service.flows.derivative",
                "editor_service.flows.netnew",
            )
        )
    except ModuleNotFoundError:
        flows_available = False
    if flows_available:
        raise RuntimeError(
            "B9 flow adapter TODO: B6/B7 are present; wire FakeLlm.script into both "
            "flows before running the mixed-mode demo"
        )

    def handler(request: SliceRequest) -> SliceReport:
        selected = [comments[requirement.id] for requirement in request.requirements]
        ops: list[DraftOp] = []
        if request.mode == Mode.NET_NEW:
            ops = [
                DraftOp(
                    kind="append",
                    requirement_id=requirement.id,
                    section_id="draft",
                    value=f"Client input reviewed for {requirement.id}",
                )
                for requirement in request.requirements
            ]
        return SliceReport(
            slice_id=request.slice_id,
            comments=selected,
            ops=ops,
            unverified=[],
            attempts_used=1,
        )

    typed_handler: Callable[[SliceRequest], Awaitable[SliceReport] | SliceReport] = handler
    return FakeSliceRunner(handler=typed_handler)


async def run_demo() -> DemoRun:
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
    runner = _runner(_fixture_comments())
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
    assert len(outbound.attachments) == 2
    assert all(requirement.id in outbound.body for requirement in manifest.requirements)
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
        checker_output=checker_output,
    )


async def _main() -> int:
    run = await run_demo()
    print("B9 e2e demo: PASS")
    print(f"RequestResult status: {run.result.status}")
    print(f"jobs done: {len(run.jobs)}; attachments: {len(run.outbound.attachments)}")
    print("requirements: " + ", ".join(requirement.id for requirement in run.manifest.requirements))
    print(run.checker_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))