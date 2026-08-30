"""Shared test helpers — building emails and archives against the shared fixture.

Per CONTEXT.md / B3-intake.md: test emails are built from
`fixtures/fleet-vehicle-return/`, never invented from scratch, so the same manifest and
photo set every other branch tests against also exercises intake.
"""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from email_service.transport import Attachment, InboundMessage
from mff_contracts import Constraint, Requirement

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ZIP_CONTENT_TYPE = "application/zip"

REPO_ROOT = Path(__file__).resolve().parents[4]
FIXTURE_ROOT = REPO_ROOT / "fixtures" / "fleet-vehicle-return"
MANIFEST_TEXT = (FIXTURE_ROOT / "manifest.txt").read_text(encoding="utf-8")
DERIVATIVE_DOCX_PATH = FIXTURE_ROOT / "input" / "derivative" / "form_supplied.docx"
NETNEW_FOLDER = FIXTURE_ROOT / "input" / "netnew" / "WN-7020U"


def make_minimal_docx(body_text: str = "hello") -> bytes:
    """A tiny, genuinely valid `.docx` (a zip containing `word/document.xml`) built
    with nothing but the standard library — no python-docx dependency needed here."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'>"
            "<Default Extension='xml' ContentType='application/xml'/>"
            "</Types>",
        )
        zf.writestr(
            "word/document.xml",
            "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
            f"<w:body><w:p><w:r><w:t>{body_text}</w:t></w:r></w:p></w:body>"
            "</w:document>",
        )
    return buf.getvalue()


def make_minimal_jpeg() -> bytes:
    """Just enough bytes to sniff as a JPEG — a real magic-number prefix."""
    return b"\xff\xd8\xff\xe0" + b"\x00" * 32


def zip_bytes(
    entries: dict[str, bytes], *, raw_infos: list[zipfile.ZipInfo] | None = None
) -> bytes:
    """Build a zip from `{path: content}`, in insertion order. `raw_infos` lets a test
    write specific `ZipInfo` objects directly (external_attr for a symlink, etc.)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
        for info in raw_infos or []:
            zf.writestr(info, b"")
    return buf.getvalue()


def zip_of_directory(root: Path) -> bytes:
    """Zip `root`'s contents, preserving its subfolder structure, with paths relative
    to `root` itself (so `root/WN-7020U/x.jpg` becomes an entry `x.jpg` at the zip's
    top level would be wrong — we want the containing folder to be `root`'s CHILD
    folders, so callers pass the *parent* of the folder(s) they want as top-level
    zip entries)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=str(path.relative_to(root)))
    return buf.getvalue()


def derivative_zip_from_fixture(*, count: int = 1) -> bytes:
    """`derivative.zip` containing `count` distinct `.docx` files, built from the
    fixture's real supplied form (or, when more than one is needed, a small synthetic
    docx per extra copy so tests stay fast)."""
    entries: dict[str, bytes] = {"form_supplied.docx": DERIVATIVE_DOCX_PATH.read_bytes()}
    for i in range(1, count):
        entries[f"extra-form-{i}.docx"] = make_minimal_docx(f"extra {i}")
    return zip_bytes(entries)


def netnew_zip_from_fixture() -> bytes:
    """`net-new.zip` containing exactly the fixture's `WN-7020U` folder."""
    return zip_of_directory(NETNEW_FOLDER.parent)


def make_inbound(**overrides: object) -> InboundMessage:
    base: dict[str, object] = {
        "message_id": "<client-1@example.test>",
        "sender": "client@example.test",
        "subject": "Zwrot pojazdu WN-7020U",
        "body": MANIFEST_TEXT,
        "received_at": datetime(2026, 8, 30, 12, 0, tzinfo=UTC),
        "attachments": [],
    }
    base.update(overrides)
    return InboundMessage.model_validate(base)


def docx_attachment(filename: str, data: bytes | None = None) -> Attachment:
    return Attachment(
        filename=filename,
        content_type=DOCX_CONTENT_TYPE,
        data=data if data is not None else make_minimal_docx(),
    )


def zip_attachment(filename: str, data: bytes) -> Attachment:
    return Attachment(filename=filename, content_type=ZIP_CONTENT_TYPE, data=data)


def golden_requirements() -> list[Requirement]:
    """The fixture's golden parse (`expected_requirements.yaml`), as `Requirement`
    objects. Hardcoded rather than loaded from the YAML: this branch must not decide
    what a manifest parse looks like, and pinning literal values here keeps this test
    file honest about what it asserts rather than deriving it from the same file the
    (out-of-scope) parser eval already checks.
    """
    return [
        Requirement(
            id="R-01",
            ordinal=12,
            text="A photograph of the engine bay, taken with the bonnet open.",
            source_span="Under the bonnet",
            source_line=2,
            expected_count=2,
            ambiguity="repeated_verbatim_in_manifest",
        ),
        Requirement(
            id="R-02",
            ordinal=30,
            text="Four photographs of the seats.",
            source_span="4x seats",
            source_line=3,
            expected_count=4,
        ),
        Requirement(
            id="R-03",
            ordinal=43,
            text="Two photographs of the vehicle taken on the diagonal.",
            source_span="2 vehicle diagonals",
            source_line=3,
            expected_count=2,
        ),
        Requirement(
            id="R-04",
            ordinal=65,
            text=(
                "Two photographs of the headliner. Each must be taken from between the front seats."
            ),
            source_span="2x headliner",
            source_line=4,
            expected_count=2,
            constraint=Constraint(
                kind="camera_position",
                value="between_front_seats",
                source_span="Headliner must be taken from between the seats",
                source_line=10,
                note="The constraint arrives on a later line than the item it qualifies.",
            ),
        ),
        Requirement(
            id="R-05",
            ordinal=99,
            text="A photograph of the windscreen taken from inside the cabin.",
            source_span="Windscreen from inside and outside",
            source_line=6,
            expected_count=1,
        ),
        Requirement(
            id="R-06",
            ordinal=99,
            text="A photograph of the windscreen taken from outside the vehicle.",
            source_span="Windscreen from inside and outside",
            source_line=6,
            expected_count=1,
        ),
        Requirement(
            id="R-07",
            ordinal=134,
            text="A photograph of the tyre tread.",
            source_span="Tyre tread",
            source_line=7,
            expected_count=1,
        ),
        Requirement(
            id="R-08",
            ordinal=146,
            text="A photograph of the boot.",
            source_span="boot photo + equipment under the lid",
            source_line=8,
            expected_count=1,
        ),
        Requirement(
            id="R-09",
            ordinal=146,
            text="A photograph of the equipment stowed under the boot lid/floor.",
            source_span="boot photo + equipment under the lid",
            source_line=8,
            expected_count=1,
        ),
        Requirement(
            id="R-10",
            ordinal=184,
            text="A photograph of the instrument cluster.",
            source_span="and the gauges",
            source_line=9,
            expected_count=1,
        ),
    ]
