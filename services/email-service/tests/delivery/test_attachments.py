"""Attachment sizing (brief: "attachment size is a constraint, not a detail") plus the
two per-status narrations `deliver()` owns beyond attachments: every `unverified`
requirement named explicitly (req 17), and `failed_forms` named when `status ==
"partial"`, using the client's own `form_id` — never an internal id.
"""

from __future__ import annotations

from email_service.delivery import deliver
from mff_contracts import JobCursor, JobRecord, RequestRecord, RequestResult, Requirement
from mff_store import InMemoryBlobStore


def _requirement(req_id: str, ordinal: int, text: str = "some requirement text") -> Requirement:
    return Requirement(id=req_id, ordinal=ordinal, text=text, source_span="span", source_line=1)


def _request(request_id: str = "req-1") -> RequestRecord:
    return RequestRecord(
        request_id=request_id,
        manifest_raw="manifest",
        requirements=[],
        job_ids=[],
        reply_to="client@example.com",
        original_message_id="<original@client>",
        status="running",
    )


# ---------------------------------------------------------------------------
# Size threshold — tested from both sides of the boundary.
# ---------------------------------------------------------------------------


async def test_document_at_exactly_the_threshold_is_attached() -> None:
    blobs = InMemoryBlobStore()
    ref = await blobs.put(b"x" * 100, content_type="application/octet-stream", kind="reviewed")
    result = RequestResult(
        request_id="req-1", status="done", documents=[ref], requirements=[], summary={"pass": 1}
    )
    message = await deliver(result, _request(), blobs=blobs, attach_threshold_bytes=100)
    assert len(message.attachments) == 1
    assert message.attachments[0].data == b"x" * 100
    assert "DOSTĘPNE POD LINKIEM" not in message.body


async def test_document_one_byte_over_the_threshold_is_linked_not_attached() -> None:
    blobs = InMemoryBlobStore()
    ref = await blobs.put(b"x" * 101, content_type="application/octet-stream", kind="reviewed")
    result = RequestResult(
        request_id="req-1", status="done", documents=[ref], requirements=[], summary={"pass": 1}
    )
    message = await deliver(result, _request(), blobs=blobs, attach_threshold_bytes=100)
    assert message.attachments == []
    assert "DOSTĘPNE POD LINKIEM" in message.body
    # InMemoryBlobStore.signed_url is a stable, inspectable stand-in built from the uri.
    assert ref.uri in message.body


async def test_the_fixtures_own_2_8mb_document_stays_below_the_default_threshold() -> None:
    """The brief's own worked example: a single reviewed document, 2.8 MB, well under
    the tighter of Gmail's 25 MB and "many corporate servers'" 10 MB ceilings."""
    blobs = InMemoryBlobStore()
    ref = await blobs.put(
        b"x" * (2_800_000), content_type="application/octet-stream", kind="reviewed"
    )
    result = RequestResult(
        request_id="req-1", status="done", documents=[ref], requirements=[], summary={"pass": 1}
    )
    message = await deliver(result, _request(), blobs=blobs)  # default threshold
    assert len(message.attachments) == 1


async def test_three_forms_clearing_gmails_ceiling_are_all_linked() -> None:
    """The brief's other worked example: three forms comfortably clear 25 MB combined,
    even though none individually crosses the default (10 MB) threshold on its own once
    the requests scale up — here each individually exceeds it, so all three link."""
    blobs = InMemoryBlobStore()
    # Distinct content per document — BlobRef dedupes by sha256, so identical bytes
    # would collapse to one object and defeat the point of this test.
    refs = []
    for i in range(3):
        refs.append(
            await blobs.put(
                bytes([i]) * 9_000_000, content_type="application/octet-stream", kind="reviewed"
            )
        )
    result = RequestResult(
        request_id="req-1", status="done", documents=refs, requirements=[], summary={"pass": 1}
    )
    message = await deliver(result, _request(), blobs=blobs, attach_threshold_bytes=8_000_000)
    assert message.attachments == []
    assert message.body.count("DOSTĘPNE POD LINKIEM") == 1
    for ref in refs:
        assert ref.uri in message.body


# ---------------------------------------------------------------------------
# unverified — req 17: named explicitly, not left to inference.
# ---------------------------------------------------------------------------


async def test_every_unverified_requirement_is_named_explicitly() -> None:
    requirements = [
        _requirement("R-05", 10, "A photograph of the tyre tread."),
        _requirement("R-09", 90, "A photograph of the equipment under the boot floor."),
    ]
    blobs = InMemoryBlobStore()
    result = RequestResult(
        request_id="req-1",
        status="done",
        documents=[],
        requirements=requirements,
        summary={"pass": 0},
        unverified=["R-05", "R-09"],
    )
    message = await deliver(result, _request(), blobs=blobs)
    assert "[R-05]" in message.body
    assert "[R-09]" in message.body
    assert "A photograph of the tyre tread." in message.body
    assert "A photograph of the equipment under the boot floor." in message.body


async def test_no_unverified_requirements_omits_the_section() -> None:
    blobs = InMemoryBlobStore()
    result = RequestResult(
        request_id="req-1", status="done", documents=[], requirements=[], summary={"pass": 1}
    )
    message = await deliver(result, _request(), blobs=blobs)
    assert "NIEZWERYFIKOWANE" not in message.body


# ---------------------------------------------------------------------------
# failed_forms — status == "partial": the client's own form_id, never an internal one.
# ---------------------------------------------------------------------------


async def test_partial_status_names_failed_forms_and_attaches_only_successes() -> None:
    blobs = InMemoryBlobStore()
    good_ref = await blobs.put(
        b"good document bytes", content_type="application/octet-stream", kind="reviewed"
    )
    result = RequestResult(
        request_id="req-1",
        status="partial",
        documents=[good_ref],
        requirements=[],
        summary={"pass": 5, "fail": 1},
        failed_forms=["broken-form.docx"],
    )
    message = await deliver(result, _request(), blobs=blobs)
    assert len(message.attachments) == 1
    assert "NIEUKOŃCZONE FORMULARZE" in message.body
    assert "broken-form.docx" in message.body
    # never an internal id such as a job_id or a blob sha256
    assert (
        good_ref.sha256
        not in message.body.split("NIEUKOŃCZONE FORMULARZE", 1)[-1].split("\n\n\n")[0]
    )


async def test_done_status_omits_the_failed_forms_section_even_if_present() -> None:
    """`failed_forms` is only narrated when `status == "partial"` — a `"done"` result
    should never show it, defensively, even if a caller populated it in error."""
    blobs = InMemoryBlobStore()
    result = RequestResult(
        request_id="req-1",
        status="done",
        documents=[],
        requirements=[],
        summary={"pass": 1},
        failed_forms=["should-not-appear.docx"],
    )
    message = await deliver(result, _request(), blobs=blobs)
    assert "NIEUKOŃCZONE FORMULARZE" not in message.body


# ---------------------------------------------------------------------------
# Mixed modes — grouped so a reader can tell which is which.
# ---------------------------------------------------------------------------


async def test_mixed_mode_documents_are_grouped_so_a_reader_can_tell_which_is_which() -> None:
    blobs = InMemoryBlobStore()
    derivative_ref = await blobs.put(
        b"derivative bytes", content_type="application/octet-stream", kind="reviewed"
    )
    netnew_ref = await blobs.put(
        b"composed bytes", content_type="application/octet-stream", kind="composed"
    )
    derivative_job = JobRecord(
        job_id="j1",
        request_id="req-1",
        form_id="form_supplied.docx",
        status="done",
        cursor=JobCursor(slice_index=1),
        document=derivative_ref,
        summary={"pass": 1},
        unverified=[],
    )
    netnew_job = JobRecord(
        job_id="j2",
        request_id="req-1",
        form_id="WN-7020U",
        status="done",
        cursor=JobCursor(slice_index=1),
        document=netnew_ref,
        summary={"pass": 1},
        unverified=[],
    )
    result = RequestResult(
        request_id="req-1",
        status="done",
        documents=[derivative_ref, netnew_ref],
        requirements=[],
        summary={"pass": 2},
    )
    message = await deliver(result, _request(), blobs=blobs, jobs=[derivative_job, netnew_job])
    body = message.body
    assert "derivative" in body
    assert "net-new" in body
    assert "form_supplied.docx" in body
    assert "WN-7020U" in body


async def test_single_mode_request_gets_no_mode_heading_clutter() -> None:
    blobs = InMemoryBlobStore()
    ref = await blobs.put(
        b"derivative bytes", content_type="application/octet-stream", kind="reviewed"
    )
    job = JobRecord(
        job_id="j1",
        request_id="req-1",
        form_id="form_supplied.docx",
        status="done",
        cursor=JobCursor(slice_index=1),
        document=ref,
        summary={"pass": 1},
        unverified=[],
    )
    result = RequestResult(
        request_id="req-1", status="done", documents=[ref], requirements=[], summary={"pass": 1}
    )
    message = await deliver(result, _request(), blobs=blobs, jobs=[job])
    assert "(derivative)" not in message.body
