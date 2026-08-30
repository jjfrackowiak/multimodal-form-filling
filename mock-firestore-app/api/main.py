import json
import os
import threading
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from google.cloud import firestore, storage

PROJECT = os.environ.get("GCP_PROJECT", "mock-project")
BUCKET = os.environ.get("BUCKET", "mock-files")
COLLECTION = os.environ.get("COLLECTION", "jobs")
PREPARE_URL = os.environ.get("PREPARE_URL", "")
PORT = int(os.environ.get("PORT", "8080"))

db = firestore.Client(project=PROJECT)
gcs = storage.Client(project=PROJECT)
app = Flask(__name__)


def now():
    return datetime.now(timezone.utc).isoformat()


def ensure_bucket():
    bucket = gcs.lookup_bucket(BUCKET)
    if bucket is None:
        bucket = gcs.create_bucket(BUCKET)
    return bucket


def post_json(url, payload, timeout=30):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode() or "{}")


def invoke_prepare(job_id):
    if not PREPARE_URL:
        return
    try:
        post_json(PREPARE_URL, {"jobId": job_id})
    except Exception as e:
        db.collection(COLLECTION).document(job_id).update(
            {
                "status": "failed",
                "step": "prepare",
                "error": f"prepare invoke failed: {e}",
                "updatedAt": now(),
            }
        )


@app.get("/health")
def health():
    return {"ok": True, "service": "api"}


@app.post("/files")
def upload():
    if "file" not in request.files:
        return {"error": "missing multipart field 'file'"}, 400
    f = request.files["file"]
    if not f.filename:
        return {"error": "empty filename"}, 400

    job_id = uuid.uuid4().hex
    object_path = f"uploads/{job_id}/{f.filename}"
    data = f.read()

    bucket = ensure_bucket()
    blob = bucket.blob(object_path)
    blob.upload_from_string(data, content_type=f.mimetype or "application/octet-stream")

    doc = {
        "id": job_id,
        "status": "uploaded",
        "step": None,
        "createdAt": now(),
        "updatedAt": now(),
        "file": {
            "bucket": BUCKET,
            "path": object_path,
            "gsUri": f"gs://{BUCKET}/{object_path}",
            "originalName": f.filename,
            "contentType": f.mimetype,
            "sizeBytes": len(data),
        },
        "result": None,
        "error": None,
    }
    db.collection(COLLECTION).document(job_id).set(doc)
    return jsonify(doc), 201


@app.post("/jobs/<job_id>/start")
def start(job_id):
    ref = db.collection(COLLECTION).document(job_id)
    snap = ref.get()
    if not snap.exists:
        return {"error": "not found"}, 404
    ref.update(
        {
            "status": "queued",
            "step": "prepare",
            "error": None,
            "updatedAt": now(),
        }
    )
    threading.Thread(target=invoke_prepare, args=(job_id,), daemon=True).start()
    return jsonify(ref.get().to_dict())


@app.get("/jobs/<job_id>")
def get_job(job_id):
    snap = db.collection(COLLECTION).document(job_id).get()
    if not snap.exists:
        return {"error": "not found"}, 404
    return jsonify(snap.to_dict())


@app.get("/jobs")
def list_jobs():
    docs = [d.to_dict() for d in db.collection(COLLECTION).stream()]
    return jsonify(docs)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, threaded=True)
