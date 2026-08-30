import json
import os
import urllib.request
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from google.cloud import firestore, storage

PROJECT = os.environ.get("GCP_PROJECT", "mock-project")
COLLECTION = os.environ.get("COLLECTION", "jobs")
CV_URL = os.environ.get("CV_URL", "")
PORT = int(os.environ.get("PORT", "8080"))

db = firestore.Client(project=PROJECT)
gcs = storage.Client(project=PROJECT)
app = Flask(__name__)


def now():
    return datetime.now(timezone.utc).isoformat()


def fail(ref, message):
    ref.update(
        {
            "status": "failed",
            "step": "prepare",
            "error": message,
            "updatedAt": now(),
        }
    )


def post_json(url, payload, timeout=60):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode() or "{}")


@app.get("/health")
def health():
    return {"ok": True, "service": "fn-prepare"}


@app.post("/")
@app.post("/prepare")
def prepare():
    body = request.get_json(silent=True) or {}
    job_id = body.get("jobId")
    if not job_id:
        return {"error": "missing jobId"}, 400

    ref = db.collection(COLLECTION).document(job_id)
    snap = ref.get()
    if not snap.exists:
        return {"error": "not found"}, 404

    data = snap.to_dict()
    status = data.get("status")
    if status in ("done", "processing"):
        return jsonify(data)

    file_meta = data.get("file") or {}
    bucket_name = file_meta.get("bucket")
    path = file_meta.get("path")
    if not bucket_name or not path:
        fail(ref, "document has no file.bucket/path")
        return jsonify(ref.get().to_dict()), 400

    blob = gcs.bucket(bucket_name).blob(path)
    if not blob.exists():
        fail(ref, f"object not found: gs://{bucket_name}/{path}")
        return jsonify(ref.get().to_dict()), 404

    blob.reload()
    ref.update(
        {
            "status": "prepared",
            "step": "prepare",
            "error": None,
            "file.contentType": blob.content_type or file_meta.get("contentType"),
            "file.sizeBytes": blob.size if blob.size is not None else file_meta.get("sizeBytes"),
            "updatedAt": now(),
        }
    )

    if CV_URL:
        try:
            post_json(CV_URL, {"jobId": job_id})
        except Exception as e:
            fail(ref, f"cv invoke failed: {e}")
            return jsonify(ref.get().to_dict()), 502

    return jsonify(ref.get().to_dict())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, threaded=True)
