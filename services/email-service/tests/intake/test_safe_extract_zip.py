"""safe_extract_zip — attacker-facing. Reject before writing, not after.

DoD #6/#7: a zip-slip archive is rejected and nothing lands outside the temp root
(asserted on the filesystem, not just the verdict), and an oversized archive is
rejected before extraction.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from intake_helpers import zip_bytes

from email_service.intake import (
    ArchiveTooLargeError,
    CorruptArchiveError,
    UnsafeArchiveError,
    safe_extract_zip,
)


def _all_files_under(root: Path) -> list[str]:
    return sorted(str(p) for p in root.rglob("*") if p.is_file())


def test_path_traversal_entry_is_rejected_and_writes_nothing_outside_root(tmp_path: Path) -> None:
    dest = tmp_path / "extract-root"
    dest.mkdir()
    malicious = zip_bytes({"../escape.docx": b"payload", "safe.txt": b"fine"})

    before = _all_files_under(tmp_path)
    with pytest.raises(UnsafeArchiveError):
        safe_extract_zip(malicious, dest)
    after = _all_files_under(tmp_path)

    # Nothing was written anywhere under tmp_path — not in dest, not beside it.
    assert before == after
    assert list(dest.iterdir()) == []


def test_absolute_path_entry_is_rejected(tmp_path: Path) -> None:
    dest = tmp_path / "extract-root"
    dest.mkdir()
    malicious = zip_bytes({"/etc/passwd": b"payload"})

    with pytest.raises(UnsafeArchiveError):
        safe_extract_zip(malicious, dest)
    assert list(dest.iterdir()) == []


def test_windows_absolute_path_entry_is_rejected(tmp_path: Path) -> None:
    dest = tmp_path / "extract-root"
    dest.mkdir()
    malicious = zip_bytes({"C:/Windows/system.ini": b"payload"})

    with pytest.raises(UnsafeArchiveError):
        safe_extract_zip(malicious, dest)
    assert list(dest.iterdir()) == []


def test_symlink_entry_is_rejected(tmp_path: Path) -> None:
    dest = tmp_path / "extract-root"
    dest.mkdir()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo("link")
        # Unix mode bits for a symlink, shifted into external_attr as zipfile expects.
        info.external_attr = 0o120777 << 16
        zf.writestr(info, "/etc/passwd")
    malicious = buf.getvalue()

    with pytest.raises(UnsafeArchiveError):
        safe_extract_zip(malicious, dest)
    assert list(dest.iterdir()) == []


def test_deeply_nested_traversal_is_also_rejected(tmp_path: Path) -> None:
    dest = tmp_path / "extract-root"
    dest.mkdir()
    malicious = zip_bytes({"a/b/../../../escape.txt": b"payload"})

    with pytest.raises(UnsafeArchiveError):
        safe_extract_zip(malicious, dest)
    assert list(dest.iterdir()) == []


def test_archive_over_entry_cap_rejected_before_extraction(tmp_path: Path) -> None:
    dest = tmp_path / "extract-root"
    dest.mkdir()
    entries = {f"file-{i}.txt": b"x" for i in range(10)}
    data = zip_bytes(entries)

    with pytest.raises(ArchiveTooLargeError):
        safe_extract_zip(data, dest, max_entries=5)
    assert list(dest.iterdir()) == []


def test_archive_over_byte_cap_rejected_before_extraction(tmp_path: Path) -> None:
    dest = tmp_path / "extract-root"
    dest.mkdir()
    data = zip_bytes({"big.bin": b"x" * 10_000})

    with pytest.raises(ArchiveTooLargeError):
        safe_extract_zip(data, dest, max_total_bytes=1_000)
    assert list(dest.iterdir()) == []


def test_corrupt_archive_raises_corrupt_archive_error(tmp_path: Path) -> None:
    dest = tmp_path / "extract-root"
    dest.mkdir()
    with pytest.raises(CorruptArchiveError):
        safe_extract_zip(b"not a zip at all", dest)
    assert list(dest.iterdir()) == []


def test_well_behaved_archive_extracts_exactly_its_contents(tmp_path: Path) -> None:
    dest = tmp_path / "extract-root"
    dest.mkdir()
    data = zip_bytes({"folder/a.txt": b"one", "folder/b.txt": b"two"})

    written = safe_extract_zip(data, dest)

    assert sorted(written) == ["folder/a.txt", "folder/b.txt"]
    assert (dest / "folder" / "a.txt").read_bytes() == b"one"
    assert (dest / "folder" / "b.txt").read_bytes() == b"two"
