"""Cloud Run HTTP tool. The editor calls POST /v1/inventory."""

from __future__ import annotations

import logging
import os
import tempfile
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request

from cv.gcs import download_uris, list_prefix, parse_gs
from cv.images import check_image_name
from cv.pipeline import build_inventory
from cv.schema import (
    Inventory,
    InventoryImage,
    InventoryRequest,
    InventoryResponse,
    ParsedChecklist,
)
from cv.vertex import LOCATION, MODEL, PROJECT

log = logging.getLogger("cv")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

MAX_IMAGES = int(os.environ.get("CV_MAX_IMAGES", "64"))

app = FastAPI(
    title="cv",
    version="1.0.0",
    description=(
        "AI-editor tool: checklist + gs:// photos → inventory. "
        "JPEG/PNG/WebP only. Images are not uploaded in the request body."
    ),
)


@app.middleware("http")
async def request_id_mw(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    request.state.request_id = rid
    resp = await call_next(request)
    resp.headers["x-request-id"] = rid
    return resp


@app.get("/health")
@app.get("/healthz")
def health():
    return {
        "ok": True,
        "service": "cv",
        "model": MODEL,
        "project": PROJECT,
        "location": LOCATION,
    }


def _dedupe(uris: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for u in uris:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _collect_uris(req: InventoryRequest) -> list[str]:
    uris = [img.uri for img in req.images]
    if req.image_prefix:
        try:
            uris.extend(list_prefix(req.image_prefix))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except Exception as e:
            log.exception("gcs list_prefix")
            raise HTTPException(502, f"gcs: {e}") from e
    uris = _dedupe(uris)
    if not uris:
        raise HTTPException(400, "images or image_prefix required")
    if len(uris) > MAX_IMAGES:
        raise HTTPException(400, f"too many images ({len(uris)} > {MAX_IMAGES})")
    for u in uris:
        try:
            _, path = parse_gs(u)
            check_image_name(path)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    return uris


def _align(requested: list[str], inv: Inventory) -> list[InventoryImage]:
    """One row per request URI, same order. Duplicates share the canonical label."""
    by_uri = {im.uri: im for im in inv.images if im.uri}
    by_name = {im.file: im for im in inv.images}
    for a, b in inv.exact_duplicate_pairs:
        if a in by_name and b not in by_name:
            by_name[b] = by_name[a]
        if b in by_name and a not in by_name:
            by_name[a] = by_name[b]
    out: list[InventoryImage] = []
    for uri in requested:
        name = Path(uri).name
        src = by_uri.get(uri) or by_name.get(name)
        if src is None:
            out.append(InventoryImage(file=name, uri=uri))
        else:
            out.append(src.model_copy(update={"file": name, "uri": uri}))
    return out


@app.post("/v1/inventory", response_model=InventoryResponse)
def inventory(req: InventoryRequest) -> InventoryResponse:
    if not req.requirements:
        raise HTTPException(400, "requirements must not be empty")
    checklist = ParsedChecklist(requirements=req.requirements)
    uris = _collect_uris(req)
    log.info("inventory images=%d prefix=%s", len(uris), bool(req.image_prefix))

    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="cv-") as tmp:
        try:
            downloaded = download_uris(uris, Path(tmp))
        except Exception as e:
            log.exception("gcs download")
            raise HTTPException(502, f"gcs: {e}") from e
        if not downloaded:
            raise HTTPException(400, "no jpeg/png/webp objects in the given uris")
        paths = [p for _, p in downloaded]
        source_uris = {p.name: uri for uri, p in downloaded}
        try:
            inv = build_inventory(
                paths,
                checklist,
                manifest_text=req.manifest,
                source_uris=source_uris,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except Exception as e:
            log.exception("inventory")
            raise HTTPException(502, f"vertex: {e}") from e
    return InventoryResponse(
        images=_align(uris, inv),
        exact_duplicate_pairs=inv.exact_duplicate_pairs,
        duration_seconds=round(time.perf_counter() - t0, 3),
        model=MODEL,
        project=PROJECT,
    )


def _job_adapter_enabled() -> bool:
    return os.environ.get("ENABLE_JOB_ADAPTER", "").lower() in {"1", "true", "yes"}


@app.post("/process")
def process_job(body: dict) -> dict:
    """Local mock glue only. Production editor calls POST /v1/inventory."""
    if not _job_adapter_enabled():
        raise HTTPException(404, "job adapter disabled; use POST /v1/inventory")
    from datetime import UTC, datetime

    from google.cloud import firestore

    job_id = body.get("jobId")
    if not job_id:
        raise HTTPException(400, "missing jobId")
    project = os.environ.get("GCP_PROJECT") or PROJECT
    coll = os.environ.get("COLLECTION", "jobs")
    db = firestore.Client(project=project)
    ref = db.collection(coll).document(job_id)
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(404, "job not found")
    data = snap.to_dict() or {}
    now = datetime.now(UTC).isoformat()
    ref.update({"status": "processing", "step": "process", "updatedAt": now, "error": None})

    checklist_raw = data.get("checklist")
    if not checklist_raw:
        ref.update({"status": "failed", "error": "job has no checklist", "updatedAt": now})
        raise HTTPException(400, "job has no checklist")
    checklist = ParsedChecklist.model_validate(checklist_raw)
    file_meta = data.get("file") or {}
    uris: list[str] = list(data.get("image_uris") or [])
    gs = file_meta.get("gsUri")
    if gs:
        uris.append(gs)
    prefix = data.get("image_prefix")
    if prefix:
        uris.extend(list_prefix(prefix))
    uris = _dedupe(uris)

    t0 = time.perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix="cv-job-") as tmp:
            downloaded = download_uris(uris, Path(tmp))
            paths = [p for _, p in downloaded]
            source_uris = {p.name: uri for uri, p in downloaded}
            inv = build_inventory(
                paths,
                checklist,
                manifest_text=data.get("manifest"),
                source_uris=source_uris,
            )
        payload = inv.model_dump(mode="json")
        ref.update(
            {
                "status": "done",
                "step": "process",
                "result": payload,
                "duration_seconds": round(time.perf_counter() - t0, 3),
                "updatedAt": datetime.now(UTC).isoformat(),
                "error": None,
            }
        )
    except Exception as e:
        log.exception("job %s", job_id)
        ref.update(
            {
                "status": "failed",
                "step": "process",
                "error": str(e),
                "updatedAt": datetime.now(UTC).isoformat(),
            }
        )
        raise HTTPException(502, str(e)) from e
    return ref.get().to_dict() or {}
