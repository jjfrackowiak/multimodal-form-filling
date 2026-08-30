import os
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from google.cloud import firestore, storage

PROJECT = os.environ.get("GCP_PROJECT", "mock-project")
COLLECTION = os.environ.get("COLLECTION", "jobs")
PORT = int(os.environ.get("PORT", "8080"))

db = firestore.Client(project=PROJECT)
gcs = storage.Client(project=PROJECT)
app = Flask(__name__)


def now():
    return datetime.now(timezone.utc).isoformat()


@app.get("/health")
def health():
    return {"ok": True, "service": "cv", "owner": "Michal"}


@app.post("/")
@app.post("/process")
def process():
    body = request.get_json(silent=True) or {}
    job_id = body.get("jobId")
    if not job_id:
        return {"error": "missing jobId"}, 400

    ref = db.collection(COLLECTION).document(job_id)
    snap = ref.get()
    if not snap.exists:
        return {"error": "not found"}, 404

    data = snap.to_dict()
    if data.get("status") == "done":
        return jsonify(data)

    file_meta = data.get("file") or {}
    bucket_name = file_meta.get("bucket")
    path = file_meta.get("path")
    if not bucket_name or not path:
        ref.update(
            {
                "status": "failed",
                "step": "process",
                "error": "document has no file.bucket/path",
                "updatedAt": now(),
            }
        )
        return jsonify(ref.get().to_dict()), 400

    ref.update(
        {
            "status": "processing",
            "step": "process",
            "error": None,
            "updatedAt": now(),
        }
    )

    try:
        raw = gcs.bucket(bucket_name).blob(path).download_as_bytes()
        preview = raw[:200].decode("utf-8", errors="replace")
        result = {
            "bytes": len(raw),
            "preview": preview,
            "note": "dummy CV — replace with image process / understand / crop",
        }
        ref.update(
            {
                "status": "done",
                "step": "process",
                "result": result,
                "error": None,
                "updatedAt": now(),
            }
        )
        print(f"done {job_id} bytes={len(raw)}", flush=True)
    except Exception as e:
        ref.update(
            {
                "status": "failed",
                "step": "process",
                "error": str(e),
                "updatedAt": now(),
            }
        )
        print(f"failed {job_id}: {e}", flush=True)
        return jsonify(ref.get().to_dict()), 500

    return jsonify(ref.get().to_dict())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, threaded=True)
