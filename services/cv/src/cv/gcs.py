"""Materialize gs:// objects to a temp dir. Honors STORAGE_EMULATOR_HOST."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from google.cloud import storage

from cv.images import is_supported_image, sniff_image_kind

_DOWNLOAD_WORKERS = 8


def _client() -> storage.Client:
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT") or "local"
    if os.environ.get("STORAGE_EMULATOR_HOST"):
        from google.auth.credentials import AnonymousCredentials

        return storage.Client(project=project, credentials=AnonymousCredentials())
    return storage.Client(project=project)


def parse_gs(uri: str) -> tuple[str, str]:
    if not uri.startswith("gs://"):
        raise ValueError(f"not a gs:// uri: {uri}")
    rest = uri[5:]
    bucket, _, path = rest.partition("/")
    if not bucket or not path:
        raise ValueError(f"bad gs uri: {uri}")
    return bucket, path


def _unique_name(path: str, used: dict[str, int]) -> str:
    name = Path(path).name or "blob"
    n = used.get(name, 0)
    used[name] = n + 1
    if not n:
        return name
    return f"{Path(name).stem}_{n}{Path(name).suffix}"


def download_uris(uris: list[str], dest: Path) -> list[tuple[str, Path]]:
    """Download image objects. Returns (gs_uri, local_path) for supported images."""
    dest.mkdir(parents=True, exist_ok=True)
    gcs = _client()
    used: dict[str, int] = {}
    jobs: list[tuple[str, str]] = []
    for uri in uris:
        _bucket, path = parse_gs(uri)
        if not is_supported_image(path):
            continue
        jobs.append((uri, _unique_name(path, used)))
    if not jobs:
        return []

    def _one(uri: str, name: str) -> tuple[str, Path] | None:
        bucket, path = parse_gs(uri)
        local = dest / name
        gcs.bucket(bucket).blob(path).download_to_filename(str(local))
        kind = sniff_image_kind(local.read_bytes()[:16])
        if kind in (None, "heic"):
            local.unlink(missing_ok=True)
            return None
        return uri, local

    out: list[tuple[str, Path]] = []
    n = max(1, min(_DOWNLOAD_WORKERS, len(jobs)))
    with ThreadPoolExecutor(max_workers=n) as pool:
        futs = [pool.submit(_one, uri, name) for uri, name in jobs]
        for fut in as_completed(futs):
            got = fut.result()
            if got is not None:
                out.append(got)
    out.sort(key=lambda item: item[1].name)
    return out


def list_prefix(gs_prefix: str) -> list[str]:
    raw = gs_prefix if gs_prefix.endswith("/") else gs_prefix + "/"
    bucket, prefix = parse_gs(raw)
    blobs = _client().bucket(bucket).list_blobs(prefix=prefix)
    uris: list[str] = []
    for b in blobs:
        if b.name.endswith("/"):
            continue
        if not is_supported_image(b.name):
            continue
        uris.append(f"gs://{bucket}/{b.name}")
    return uris
