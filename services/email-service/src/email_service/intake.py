"""Turn an inbound message into a job list or a rejection — reqs 3, 6, 7, 8.

**This module must never parse the manifest.** `Requirement`s only ever come from the
editor's 202 (`RequestAccepted.requirements`) — see `replies.render_confirmation`. Two
parses of the same manifest can differ (the parser has a model in it); if intake produced
its own list, the client could be shown one parse while their document is graded against
another. `import-linter`'s "no module outside llm/ and agents/ imports a model library"
contract enforces this at the workspace level; `tests/intake/test_no_model_library.py`
pins it for this module specifically.

**The manifest is always the email body**, never an attachment — `InboundMessage.body`
copies straight into `ParsedRequest.manifest_raw`, byte-for-byte, because
`Requirement.source_span` will later quote from it.

**Attachments are work items.** A bare `.docx` is one DERIVATIVE job. `derivative.zip`
unpacks to one DERIVATIVE job per `.docx` inside. `net-new.zip` / `netnew.zip` unpacks to
one NET-NEW job per top-level folder — the folder name becomes `form_id`, its `.txt`
files become `ClientInputs.texts`, its images become that job's raw image material.
Containment (which folder an image sits in) is the only way a client expresses what
belongs to what; there is no naming convention to invent.

`ParsedJob` mirrors `mff_contracts.JobRequest`'s own derivative/net-new split (`mode`
paired with either `form` or `inputs`, never both) but is intake's own type, not that
contract: a `JobRequest` needs a `job_id`, a `request_id`, requirements already filtered
by `applies_to`, and images already run through vision — all of which belong to the
orchestrator (B5), not intake. `ParsedJob.form`/`.inputs` carry raw bytes read back off
disk after safe extraction; nothing here touches the blob store.

Every attachment is content-sniffed, never trusted by extension: a `.docx`-named file
that is actually a PDF is rejected, and a real `.docx` saved under the wrong extension is
still accepted. Zip extraction validates every `zipfile.ZipInfo` before writing anything
— path traversal, absolute paths and symlinks are rejected outright, and the entry count
and total uncompressed size are checked against a cap *before* any bytes are
decompressed. `extractall` is never used on untrusted input.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import stat
import tempfile
import zipfile
from datetime import UTC, datetime, timedelta
from email.header import decode_header, make_header
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from mff_contracts import ClientInputs, IntakeProblem, IntakeVerdict, Mode

from .transport import Attachment, InboundMessage

__all__ = [
    "DEFAULT_MAX_ARCHIVE_BYTES",
    "DEFAULT_MAX_ARCHIVE_ENTRIES",
    "ArchiveTooLargeError",
    "CorruptArchiveError",
    "ParsedForm",
    "ParsedJob",
    "ParsedNetNewInputs",
    "ParsedRequest",
    "RateLimiter",
    "UnsafeArchiveError",
    "allowed_senders_from_env",
    "parse_inbound",
    "safe_extract_zip",
    "validate_intake",
]

# ---------------------------------------------------------------------------
# Intake's own DTOs — deliberately not mff_contracts.JobRequest. See module docstring.
# ---------------------------------------------------------------------------


class ParsedForm(BaseModel):
    """A bare `.docx` attachment, or one `.docx` unpacked from `derivative.zip`."""

    filename: str
    data: bytes


class ParsedNetNewInputs(BaseModel):
    """One folder from a net-new zip: text content plus raw, not-yet-analysed images."""

    inputs: ClientInputs  # set_id is the folder name; texts keyed by filename
    images: list[Attachment] = Field(default_factory=list)


class ParsedJob(BaseModel):
    """One work item: a form to validate, or a folder of inputs to compose from.

    Mirrors `JobRequest`'s own invariant (mode paired with the matching payload, never
    both) so a later stage can lift a `ParsedJob` into a real `JobRequest` without
    reconciling two different shapes.
    """

    mode: Mode
    form_id: str  # the .docx filename, or the input folder name — the client's own label
    form: ParsedForm | None = None
    inputs: ParsedNetNewInputs | None = None

    @model_validator(mode="after")
    def _mode_matches_payload(self) -> ParsedJob:
        if self.mode == Mode.DERIVATIVE and (self.form is None or self.inputs is not None):
            raise ValueError("ParsedJob: derivative mode requires form and no inputs")
        if self.mode == Mode.NET_NEW and (self.inputs is None or self.form is not None):
            raise ValueError("ParsedJob: net_new mode requires inputs and no form")
        return self


class ParsedRequest(BaseModel):
    """One client email, syntactically parsed. Not yet a verdict — see `validate_intake`."""

    message_id: str
    sender: str
    subject: str
    manifest_raw: str  # the body, byte-for-byte — never parsed here
    attachment_count: int = 0
    jobs: list[ParsedJob] = Field(default_factory=list)
    # Problems discovered while parsing attachments (bad archive, wrong format, …).
    # validate_intake folds these together with the checks it owns (sender, rate,
    # manifest presence) into one IntakeVerdict.
    problems: list[IntakeProblem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Content sniffing — never trust the extension.
# ---------------------------------------------------------------------------

_ZIP_MAGIC_PREFIXES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
_DOCX_MARKER = "word/document.xml"


def _is_zip_bytes(data: bytes) -> bool:
    if not data.startswith(_ZIP_MAGIC_PREFIXES):
        return False
    try:
        return zipfile.is_zipfile(io.BytesIO(data))
    except OSError:
        return False


def _looks_like_docx(data: bytes) -> bool:
    """A `.docx` is a zip that contains `word/document.xml` — nothing else qualifies."""
    if not _is_zip_bytes(data):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return _DOCX_MARKER in zf.namelist()
    except zipfile.BadZipFile:
        return False


def _looks_like_zip(data: bytes) -> bool:
    return _is_zip_bytes(data)


def _sniff_image_content_type(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith(b"BM"):
        return "image/bmp"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    return None


def _decode_rfc2047(value: str) -> str:
    """Undo RFC 2047 encoded-words in a filename/subject/sender.

    Defence in depth: `ImapSmtpTransport` already decodes these before an
    `InboundMessage` exists (see `transport/mime.py`), but nothing stops another
    `MailTransport` implementation, or a test, from handing intake a raw encoded-word
    string directly — and `protocol.docx` arriving as gibberish fails a content check
    on a perfectly valid file.
    """
    if not value or "=?" not in value:
        return value
    try:
        return str(make_header(decode_header(value)))
    except (LookupError, UnicodeDecodeError, ValueError):
        return value


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1250"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


def _archive_kind(filename: str) -> Literal["derivative", "netnew"] | None:
    stem = Path(filename).stem.strip().lower()
    if stem == "derivative":
        return "derivative"
    if stem in {"net-new", "netnew", "net_new"}:
        return "netnew"
    return None


# ---------------------------------------------------------------------------
# Unzipping — attacker-facing. Validate every entry before writing anything.
# ---------------------------------------------------------------------------


class UnsafeArchiveError(Exception):
    """A zip entry attempts path traversal or an absolute path, or is a symlink."""


class ArchiveTooLargeError(Exception):
    """The archive declares more entries, or more uncompressed bytes, than the cap."""


class CorruptArchiveError(Exception):
    """The bytes are not a zip archive `zipfile` can read."""


DEFAULT_MAX_ARCHIVE_ENTRIES = 2000
DEFAULT_MAX_ARCHIVE_BYTES = 200 * 1024 * 1024  # 200 MiB — generous; a bomb is often a
# plausible accident (a folder of RAW photos zipped without thinking) as much as an
# attack, so this is a sanity cap, not a tight budget.


def safe_extract_zip(
    data: bytes,
    dest: Path,
    *,
    max_entries: int = DEFAULT_MAX_ARCHIVE_ENTRIES,
    max_total_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES,
) -> list[str]:
    """Extract `data` into `dest`, an existing directory the caller controls.

    Every `ZipInfo` is validated — no path traversal, no absolute path, no symlink —
    and the archive's declared entry count and total uncompressed size are checked
    against the caps, all *before* a single entry is decompressed. Extraction happens
    only after every entry has passed; a rejected archive writes nothing.

    Returns the paths written, relative to `dest`. Raises `CorruptArchiveError`,
    `ArchiveTooLargeError` or `UnsafeArchiveError` instead of ever writing outside
    `dest`.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise CorruptArchiveError(str(exc)) from exc

    with zf:
        infolist = zf.infolist()
        if len(infolist) > max_entries:
            raise ArchiveTooLargeError(f"{len(infolist)} entries exceeds the cap of {max_entries}")
        total_bytes = sum(info.file_size for info in infolist)
        if total_bytes > max_total_bytes:
            raise ArchiveTooLargeError(
                f"{total_bytes} uncompressed bytes exceeds the cap of {max_total_bytes}"
            )

        dest_root = dest.resolve()
        targets: list[tuple[zipfile.ZipInfo, Path]] = []
        for info in infolist:
            name = info.filename.replace("\\", "/")
            posix_name = PurePosixPath(name)
            if (
                not name
                or posix_name.is_absolute()
                or re.match(r"^[A-Za-z]:", name)
                or any(part == ".." for part in posix_name.parts)
            ):
                raise UnsafeArchiveError(f"unsafe path in archive: {info.filename!r}")
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise UnsafeArchiveError(f"symlink entry in archive: {info.filename!r}")
            target = (dest_root / posix_name).resolve()
            if not target.is_relative_to(dest_root):
                raise UnsafeArchiveError(f"entry escapes extraction root: {info.filename!r}")
            targets.append((info, target))

        written: list[str] = []
        for info, target in targets:
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            written.append(str(target.relative_to(dest_root)))
        return written


def _derivative_zip_to_jobs(
    dest: Path, archive_name: str
) -> tuple[list[ParsedJob], IntakeProblem | None]:
    entries = sorted(p for p in dest.iterdir() if p.is_file() and p.suffix.lower() == ".docx")
    jobs: list[ParsedJob] = []
    for entry in entries:
        data = entry.read_bytes()
        if not _looks_like_docx(data):
            continue
        jobs.append(
            ParsedJob(
                mode=Mode.DERIVATIVE,
                form_id=entry.name,
                form=ParsedForm(filename=entry.name, data=data),
            )
        )
    if not jobs:
        return [], IntakeProblem(
            code="empty_archive",
            detail=(
                f"'{archive_name}' does not contain any usable .docx files — add at "
                "least one Word form to the archive."
            ),
        )
    return jobs, None


def _netnew_zip_to_jobs(
    dest: Path, archive_name: str
) -> tuple[list[ParsedJob], IntakeProblem | None]:
    top_entries = sorted(dest.iterdir())
    if not top_entries:
        return [], IntakeProblem(
            code="empty_archive",
            detail=(
                f"'{archive_name}' is empty — add a folder of inputs for each form "
                "you want composed."
            ),
        )
    folders = [p for p in top_entries if p.is_dir()]
    if not folders:
        return [], IntakeProblem(
            code="unstructured_inputs",
            detail=(
                f"'{archive_name}' contains loose files at its root instead of "
                "folders — put each set of inputs in its own top-level folder "
                "(e.g. pojazd-A/) and re-zip."
            ),
        )
    jobs: list[ParsedJob] = []
    for folder in folders:
        texts: dict[str, str] = {}
        images: list[Attachment] = []
        for file_path in sorted(folder.rglob("*")):
            if not file_path.is_file():
                continue
            data = file_path.read_bytes()
            if file_path.suffix.lower() == ".txt":
                texts[file_path.name] = _decode_text(data)
                continue
            content_type = _sniff_image_content_type(data)
            if content_type is not None:
                images.append(
                    Attachment(filename=file_path.name, content_type=content_type, data=data)
                )
        if not texts and not images:
            continue
        jobs.append(
            ParsedJob(
                mode=Mode.NET_NEW,
                form_id=folder.name,
                inputs=ParsedNetNewInputs(
                    inputs=ClientInputs(set_id=folder.name, texts=texts),
                    images=images,
                ),
            )
        )
    if not jobs:
        return [], IntakeProblem(
            code="empty_archive",
            detail=(
                f"'{archive_name}' has folders but none contain any .txt files or "
                "images — add input material to at least one folder."
            ),
        )
    return jobs, None


# ---------------------------------------------------------------------------
# parse_inbound — syntax only, never the manifest's meaning.
# ---------------------------------------------------------------------------


def parse_inbound(
    msg: InboundMessage,
    *,
    max_archive_entries: int = DEFAULT_MAX_ARCHIVE_ENTRIES,
    max_archive_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES,
) -> ParsedRequest:
    """Turn a raw inbound message into work items. Never raises on attacker-controlled
    input — problems are recorded on `ParsedRequest.problems` for `validate_intake` to
    surface, so a hostile attachment always produces a rejection, never a crash.
    """
    jobs: list[ParsedJob] = []
    problems: list[IntakeProblem] = []

    for attachment in msg.attachments:
        filename = _decode_rfc2047(attachment.filename)
        data = attachment.data

        if _looks_like_docx(data):
            jobs.append(
                ParsedJob(
                    mode=Mode.DERIVATIVE,
                    form_id=filename,
                    form=ParsedForm(filename=filename, data=data),
                )
            )
            continue

        if _looks_like_zip(data):
            kind = _archive_kind(filename)
            if kind is None:
                problems.append(
                    IntakeProblem(
                        code="unsupported_format",
                        detail=(
                            f"'{filename}' is a zip archive but its name does not say "
                            "what kind of work it contains — name it 'derivative.zip' "
                            "for forms to validate or 'net-new.zip' for input folders."
                        ),
                    )
                )
                continue
            try:
                with tempfile.TemporaryDirectory(prefix="mff-intake-") as tmp:
                    dest = Path(tmp)
                    safe_extract_zip(
                        data,
                        dest,
                        max_entries=max_archive_entries,
                        max_total_bytes=max_archive_bytes,
                    )
                    if kind == "derivative":
                        sub_jobs, problem = _derivative_zip_to_jobs(dest, filename)
                    else:
                        sub_jobs, problem = _netnew_zip_to_jobs(dest, filename)
                jobs.extend(sub_jobs)
                if problem is not None:
                    problems.append(problem)
            except UnsafeArchiveError as exc:
                problems.append(
                    IntakeProblem(
                        code="unsafe_archive",
                        detail=(
                            f"'{filename}' contains an unsafe entry ({exc}) — remove "
                            "any absolute paths, '../' segments or symlinks and re-zip."
                        ),
                    )
                )
            except ArchiveTooLargeError as exc:
                problems.append(
                    IntakeProblem(
                        code="archive_too_large",
                        detail=(
                            f"'{filename}' is too large ({exc}) — split it into smaller archives."
                        ),
                    )
                )
            except CorruptArchiveError as exc:
                problems.append(
                    IntakeProblem(
                        code="unsupported_format",
                        detail=(
                            f"'{filename}' could not be read as a zip archive ({exc}) "
                            "— it may be corrupt. Re-zip and resend."
                        ),
                    )
                )
            continue

        problems.append(
            IntakeProblem(
                code="unsupported_format",
                detail=(
                    f"'{filename}' is not a .docx file or a recognised zip archive "
                    "(derivative.zip / net-new.zip / netnew.zip). v1 supports Word "
                    "forms only."
                ),
            )
        )

    return ParsedRequest(
        message_id=msg.message_id,
        sender=_decode_rfc2047(msg.sender),
        subject=_decode_rfc2047(msg.subject),
        manifest_raw=msg.body,
        attachment_count=len(msg.attachments),
        jobs=jobs,
        problems=problems,
    )


# ---------------------------------------------------------------------------
# validate_intake — req 6/8: every rejection says exactly what to add or change.
# ---------------------------------------------------------------------------


def allowed_senders_from_env(
    env: os._Environ[str] | dict[str, str] | None = None,
) -> frozenset[str]:
    """`ALLOWED_SENDERS` empty (or unset) means *closed*, not open — an empty allowlist
    that let everyone through would make this service an open robot that answers spam
    and can bounce-loop with another autoresponder."""
    e = env if env is not None else os.environ
    raw = e.get("ALLOWED_SENDERS", "")
    return frozenset(addr.strip().lower() for addr in raw.split(",") if addr.strip())


class RateLimiter:
    """A plain fixed-window request cap, per sender.

    Rate limiting needs state that outlives a single email — something a pure
    `validate_intake(req) -> IntakeVerdict` call cannot own by itself. A caller (the
    orchestrator's poll loop, or a test) holds one `RateLimiter` instance across many
    calls and passes it in; `validate_intake` treats a caller that passes none as
    "no cap enforced here."
    """

    def __init__(self, *, max_requests: int = 20, window: timedelta = timedelta(hours=1)) -> None:
        if max_requests < 1:
            raise ValueError("max_requests must be at least 1")
        self._max_requests = max_requests
        self._window = window
        self._hits: dict[str, list[datetime]] = {}

    def allow(self, sender: str, *, now: datetime | None = None) -> bool:
        moment = now if now is not None else datetime.now(UTC)
        cutoff = moment - self._window
        hits = [t for t in self._hits.get(sender, []) if t > cutoff]
        allowed = len(hits) < self._max_requests
        hits.append(moment)
        self._hits[sender] = hits
        return allowed


def validate_intake(
    req: ParsedRequest,
    *,
    allowed_senders: frozenset[str] | None = None,
    rate_limiter: RateLimiter | None = None,
    now: datetime | None = None,
) -> IntakeVerdict:
    """Fold `req.problems` (discovered while parsing attachments) together with the
    checks this function owns — sender allowlist, rate cap, manifest presence, and
    whether there was any work item at all — into one verdict.

    All-or-nothing: any problem rejects the whole request. `IntakeVerdict` is one
    verdict per email, not one per job, so a request that is half fine and half broken
    still needs the client to fix the broken half and resend the lot.
    """
    problems: list[IntakeProblem] = list(req.problems)

    senders = allowed_senders if allowed_senders is not None else allowed_senders_from_env()
    sender_key = req.sender.strip().lower()
    if sender_key not in senders:
        problems.append(
            IntakeProblem(
                code="sender_not_allowed",
                detail=(
                    f"This mailbox does not accept mail from '{req.sender}'. Ask an "
                    "administrator to add this address to ALLOWED_SENDERS."
                ),
            )
        )
    elif rate_limiter is not None and not rate_limiter.allow(sender_key, now=now):
        problems.append(
            IntakeProblem(
                code="rate_limited",
                detail=(
                    f"Too many requests from '{req.sender}' recently — wait before "
                    "sending another one."
                ),
            )
        )

    if not req.manifest_raw:
        problems.append(
            IntakeProblem(
                code="missing_manifest",
                detail=(
                    "The email body was empty. Write the manifest — what the form "
                    "must contain — in the body of the email, not as an attachment."
                ),
            )
        )
    elif not req.manifest_raw.strip():
        problems.append(
            IntakeProblem(
                code="empty_manifest",
                detail=(
                    "The email body contained only whitespace. Write the manifest "
                    "text in the body of the email."
                ),
            )
        )

    if req.attachment_count == 0:
        problems.append(
            IntakeProblem(
                code="no_work_items",
                detail=(
                    "No attachment was found. Attach a .docx form to validate, or a "
                    "derivative.zip / net-new.zip archive of forms and input folders."
                ),
            )
        )

    return IntakeVerdict(valid=not problems, problems=problems)
