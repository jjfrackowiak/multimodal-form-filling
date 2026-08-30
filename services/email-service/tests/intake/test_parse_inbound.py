"""parse_inbound — attachments become work items; the manifest is never touched."""

from __future__ import annotations

import pytest
from intake_helpers import (
    DERIVATIVE_DOCX_PATH,
    DOCX_CONTENT_TYPE,
    MANIFEST_TEXT,
    NETNEW_FOLDER,
    derivative_zip_from_fixture,
    docx_attachment,
    make_inbound,
    make_minimal_docx,
    netnew_zip_from_fixture,
    zip_attachment,
)

from email_service.intake import ParsedForm, ParsedJob, ParsedNetNewInputs, parse_inbound
from email_service.transport import Attachment
from mff_contracts import ClientInputs, Mode


def test_body_becomes_manifest_raw_byte_for_byte() -> None:
    """The manifest is always the body — never an attachment, never re-encoded."""
    parsed = parse_inbound(make_inbound(body=MANIFEST_TEXT))
    assert parsed.manifest_raw == MANIFEST_TEXT


def test_bare_docx_attachment_is_one_derivative_job() -> None:
    data = DERIVATIVE_DOCX_PATH.read_bytes()
    msg = make_inbound(attachments=[docx_attachment("form_supplied.docx", data)])
    parsed = parse_inbound(msg)

    assert parsed.attachment_count == 1
    assert len(parsed.jobs) == 1
    job = parsed.jobs[0]
    assert job.mode == Mode.DERIVATIVE
    assert job.form_id == "form_supplied.docx"
    assert job.form is not None
    assert job.form.data == data
    assert job.inputs is None
    assert parsed.problems == []


def test_derivative_zip_from_fixture_is_one_job_per_docx() -> None:
    msg = make_inbound(
        attachments=[zip_attachment("derivative.zip", derivative_zip_from_fixture())]
    )
    parsed = parse_inbound(msg)

    assert parsed.problems == []
    assert len(parsed.jobs) == 1
    job = parsed.jobs[0]
    assert job.mode == Mode.DERIVATIVE
    assert job.form_id == "form_supplied.docx"
    assert job.form is not None
    assert job.form.data == DERIVATIVE_DOCX_PATH.read_bytes()


def test_netnew_zip_from_fixture_is_one_job_with_form_id_from_folder_name() -> None:
    """input/netnew/WN-7020U/ zipped as net-new.zip -> form_id WN-7020U, its two .txt
    files become ClientInputs.texts, its 17 images become raw image material."""
    msg = make_inbound(attachments=[zip_attachment("net-new.zip", netnew_zip_from_fixture())])
    parsed = parse_inbound(msg)

    assert parsed.problems == []
    assert len(parsed.jobs) == 1
    job = parsed.jobs[0]
    assert job.mode == Mode.NET_NEW
    assert job.form_id == "WN-7020U"
    assert job.form is None
    assert job.inputs is not None
    assert job.inputs.inputs.set_id == "WN-7020U"

    txt_files_on_disk = sorted(p.name for p in NETNEW_FOLDER.glob("*.txt"))
    assert sorted(job.inputs.inputs.texts) == txt_files_on_disk
    assert job.inputs.inputs.texts["uwagi.txt"] == (NETNEW_FOLDER / "uwagi.txt").read_text(
        encoding="utf-8"
    )

    jpg_files_on_disk = list(NETNEW_FOLDER.glob("*.jpg"))
    assert len(jpg_files_on_disk) == 17
    assert len(job.inputs.images) == 17
    assert {img.filename for img in job.inputs.images} == {p.name for p in jpg_files_on_disk}
    assert all(img.content_type == "image/jpeg" for img in job.inputs.images)


def test_netnew_zip_also_accepted_when_named_netnew_without_hyphen() -> None:
    msg = make_inbound(attachments=[zip_attachment("netnew.zip", netnew_zip_from_fixture())])
    parsed = parse_inbound(msg)
    assert parsed.problems == []
    assert len(parsed.jobs) == 1
    assert parsed.jobs[0].form_id == "WN-7020U"


def test_mixed_derivative_and_netnew_in_one_email() -> None:
    """Three forms plus four input sets is seven jobs, one request — here, the
    simplest version of that: one derivative job and one net-new job together."""
    msg = make_inbound(
        attachments=[
            zip_attachment("derivative.zip", derivative_zip_from_fixture()),
            zip_attachment("net-new.zip", netnew_zip_from_fixture()),
        ]
    )
    parsed = parse_inbound(msg)

    assert parsed.problems == []
    assert len(parsed.jobs) == 2
    modes = {job.mode for job in parsed.jobs}
    assert modes == {Mode.DERIVATIVE, Mode.NET_NEW}


def test_seven_job_case_three_derivative_four_netnew() -> None:
    """DoD #5: a 3-form derivative.zip and a 4-set net-new.zip -> 7 jobs, 3 derivative
    with `form` set, 4 net-new with `inputs` set, form_id matching filenames/folders."""
    derivative = derivative_zip_from_fixture(count=3)

    import zipfile as _zipfile
    from io import BytesIO

    net_new_buf = BytesIO()
    with _zipfile.ZipFile(net_new_buf, "w", _zipfile.ZIP_DEFLATED) as zf:
        for i in range(1, 5):
            folder = f"pojazd-{i}"
            zf.writestr(f"{folder}/notes.txt", f"notes for {folder}")
            zf.writestr(f"{folder}/photo.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 16)
    net_new = net_new_buf.getvalue()

    msg = make_inbound(
        attachments=[
            zip_attachment("derivative.zip", derivative),
            zip_attachment("net-new.zip", net_new),
        ]
    )
    parsed = parse_inbound(msg)

    assert parsed.problems == []
    assert len(parsed.jobs) == 7

    derivative_jobs = [j for j in parsed.jobs if j.mode == Mode.DERIVATIVE]
    net_new_jobs = [j for j in parsed.jobs if j.mode == Mode.NET_NEW]
    assert len(derivative_jobs) == 3
    assert len(net_new_jobs) == 4

    assert {j.form_id for j in derivative_jobs} == {
        "form_supplied.docx",
        "extra-form-1.docx",
        "extra-form-2.docx",
    }
    for job in derivative_jobs:
        assert job.form is not None
        assert job.inputs is None

    assert {j.form_id for j in net_new_jobs} == {"pojazd-1", "pojazd-2", "pojazd-3", "pojazd-4"}
    for job in net_new_jobs:
        assert job.inputs is not None
        assert job.form is None
        assert job.inputs.inputs.set_id == job.form_id
        assert job.inputs.inputs.texts == {"notes.txt": f"notes for {job.form_id}"}
        assert len(job.inputs.images) == 1


def test_no_attachments_means_zero_jobs_and_no_parse_problem() -> None:
    """Zero attachments is not itself a parse-time problem — validate_intake's
    `no_work_items` check owns that call, since it needs to distinguish it from
    'something was attached but unusable'."""
    parsed = parse_inbound(make_inbound(attachments=[]))
    assert parsed.jobs == []
    assert parsed.problems == []
    assert parsed.attachment_count == 0


def test_unsupported_attachment_is_flagged_not_silently_dropped() -> None:
    msg = make_inbound(
        attachments=[Attachment(filename="notes.txt", content_type="text/plain", data=b"hello")]
    )
    parsed = parse_inbound(msg)
    assert parsed.jobs == []
    assert len(parsed.problems) == 1
    assert parsed.problems[0].code == "unsupported_format"
    assert "notes.txt" in parsed.problems[0].detail


def test_zip_with_unrecognised_name_is_unsupported_format() -> None:
    msg = make_inbound(attachments=[zip_attachment("archive.zip", derivative_zip_from_fixture())])
    parsed = parse_inbound(msg)
    assert parsed.jobs == []
    assert len(parsed.problems) == 1
    assert parsed.problems[0].code == "unsupported_format"


def test_pdf_named_docx_is_rejected_content_sniffed_not_trusted_by_name() -> None:
    fake_pdf = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< >>\nendobj\n"
    msg = make_inbound(attachments=[docx_attachment("report.docx", fake_pdf)])
    parsed = parse_inbound(msg)
    assert parsed.jobs == []
    assert len(parsed.problems) == 1
    assert parsed.problems[0].code == "unsupported_format"


def test_real_docx_with_wrong_extension_is_still_accepted() -> None:
    """Content sniffing, not extension: a genuine .docx saved as .bin is still a
    derivative job."""
    data = make_minimal_docx("real content")
    msg = make_inbound(
        attachments=[
            Attachment(filename="upload.bin", content_type="application/octet-stream", data=data)
        ]
    )
    parsed = parse_inbound(msg)
    assert parsed.problems == []
    assert len(parsed.jobs) == 1
    assert parsed.jobs[0].mode == Mode.DERIVATIVE
    assert parsed.jobs[0].form_id == "upload.bin"


def test_rfc2047_encoded_polish_filename_is_decoded() -> None:
    """`protokół.docx` RFC 2047 encoded must decode correctly, not arrive as
    gibberish that then fails a content check on a valid file."""
    encoded = "=?UTF-8?B?cHJvdG9rw7PFgi5kb2N4?="  # "protokół.docx"
    msg = make_inbound(
        attachments=[
            Attachment(filename=encoded, content_type=DOCX_CONTENT_TYPE, data=make_minimal_docx())
        ]
    )
    parsed = parse_inbound(msg)
    assert parsed.problems == []
    assert len(parsed.jobs) == 1
    assert parsed.jobs[0].form_id == "protokół.docx"


def test_empty_derivative_zip_reports_empty_archive() -> None:
    import zipfile as _zipfile
    from io import BytesIO

    buf = BytesIO()
    with _zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "no forms here")
    msg = make_inbound(attachments=[zip_attachment("derivative.zip", buf.getvalue())])
    parsed = parse_inbound(msg)
    assert parsed.jobs == []
    assert len(parsed.problems) == 1
    assert parsed.problems[0].code == "empty_archive"


def test_derivative_zip_skips_entries_that_sniff_as_not_docx() -> None:
    """A `.docx`-named zip member whose content is not actually a docx is skipped
    (content-sniffed inside the archive too), not fatally rejected while a good entry
    sits right next to it."""
    import zipfile as _zipfile
    from io import BytesIO

    buf = BytesIO()
    with _zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("real.docx", make_minimal_docx())
        zf.writestr("fake.docx", b"not actually a docx")
    msg = make_inbound(attachments=[zip_attachment("derivative.zip", buf.getvalue())])
    parsed = parse_inbound(msg)

    assert parsed.problems == []
    assert len(parsed.jobs) == 1
    assert parsed.jobs[0].form_id == "real.docx"


def test_netnew_nested_subfolder_entries_are_ignored() -> None:
    """Only files directly under a top-level folder become texts/images; a directory
    entry inside it is neither, and is skipped rather than crashing."""
    import zipfile as _zipfile
    from io import BytesIO

    buf = BytesIO()
    with _zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("pojazd-A/", "")  # explicit directory entry
        zf.writestr("pojazd-A/notes.txt", "hello")
    msg = make_inbound(attachments=[zip_attachment("net-new.zip", buf.getvalue())])
    parsed = parse_inbound(msg)

    assert parsed.problems == []
    assert len(parsed.jobs) == 1
    assert parsed.jobs[0].inputs is not None
    assert parsed.jobs[0].inputs.inputs.texts == {"notes.txt": "hello"}


def test_netnew_folder_with_no_recognised_content_is_skipped_but_others_still_work() -> None:
    import zipfile as _zipfile
    from io import BytesIO

    buf = BytesIO()
    with _zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("useless/notes.pdf", b"%PDF-1.4 not a txt or image")
        zf.writestr("useful/notes.txt", "real content")
    msg = make_inbound(attachments=[zip_attachment("net-new.zip", buf.getvalue())])
    parsed = parse_inbound(msg)

    assert parsed.problems == []
    assert len(parsed.jobs) == 1
    assert parsed.jobs[0].form_id == "useful"


def test_netnew_folder_all_folders_empty_reports_empty_archive() -> None:
    import zipfile as _zipfile
    from io import BytesIO

    buf = BytesIO()
    with _zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("empty-folder/notes.pdf", b"%PDF-1.4 unusable content")
    msg = make_inbound(attachments=[zip_attachment("net-new.zip", buf.getvalue())])
    parsed = parse_inbound(msg)

    assert parsed.jobs == []
    assert len(parsed.problems) == 1
    assert parsed.problems[0].code == "empty_archive"


def test_non_jpeg_image_formats_are_sniffed_by_content() -> None:
    import zipfile as _zipfile
    from io import BytesIO

    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    gif = b"GIF89a" + b"\x00" * 16
    bmp = b"BM" + b"\x00" * 16
    webp = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 16
    tiff = b"II*\x00" + b"\x00" * 16

    buf = BytesIO()
    with _zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("set/a.png", png)
        zf.writestr("set/b.gif", gif)
        zf.writestr("set/c.bmp", bmp)
        zf.writestr("set/d.webp", webp)
        zf.writestr("set/e.tiff", tiff)
    msg = make_inbound(attachments=[zip_attachment("net-new.zip", buf.getvalue())])
    parsed = parse_inbound(msg)

    assert parsed.problems == []
    job = parsed.jobs[0]
    assert job.inputs is not None
    content_types = {img.filename: img.content_type for img in job.inputs.images}
    assert content_types == {
        "a.png": "image/png",
        "b.gif": "image/gif",
        "c.bmp": "image/bmp",
        "d.webp": "image/webp",
        "e.tiff": "image/tiff",
    }


def test_txt_file_decoded_from_cp1250_when_not_valid_utf8() -> None:
    """Real client text is messier than UTF-8 — a Polish Windows text file saved in
    cp1250 must still decode, not come back replaced with garbage."""
    import zipfile as _zipfile
    from io import BytesIO

    polish_text = "usterka na błotniku"
    buf = BytesIO()
    with _zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("pojazd-A/uwagi.txt", polish_text.encode("cp1250"))
    msg = make_inbound(attachments=[zip_attachment("net-new.zip", buf.getvalue())])
    parsed = parse_inbound(msg)

    assert parsed.problems == []
    assert parsed.jobs[0].inputs is not None
    assert parsed.jobs[0].inputs.inputs.texts["uwagi.txt"] == polish_text


def test_parsed_job_rejects_derivative_mode_without_form() -> None:
    with pytest.raises(ValueError, match="derivative mode requires form"):
        ParsedJob(mode=Mode.DERIVATIVE, form_id="x")


def test_parsed_job_rejects_derivative_mode_with_inputs_too() -> None:
    with pytest.raises(ValueError, match="derivative mode requires form"):
        ParsedJob(
            mode=Mode.DERIVATIVE,
            form_id="x",
            form=ParsedForm(filename="x.docx", data=b"x"),
            inputs=ParsedNetNewInputs(inputs=ClientInputs(set_id="x", texts={})),
        )


def test_parsed_job_rejects_net_new_mode_without_inputs() -> None:
    with pytest.raises(ValueError, match="net_new mode requires inputs"):
        ParsedJob(mode=Mode.NET_NEW, form_id="x")


def test_netnew_zip_of_loose_files_reports_unstructured_inputs() -> None:
    import zipfile as _zipfile
    from io import BytesIO

    buf = BytesIO()
    with _zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("notes.txt", "loose, not in a folder")
        zf.writestr("photo.jpg", b"\xff\xd8\xff\xe0")
    msg = make_inbound(attachments=[zip_attachment("net-new.zip", buf.getvalue())])
    parsed = parse_inbound(msg)
    assert parsed.jobs == []
    assert len(parsed.problems) == 1
    assert parsed.problems[0].code == "unstructured_inputs"
