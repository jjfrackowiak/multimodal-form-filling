import os
import time
from datetime import datetime, timezone

from google.cloud import firestore, storage
from google.cloud.firestore_v1.base_query import FieldFilter

PROJECT = os.environ.get("GCP_PROJECT", "mock-project")
BUCKET = os.environ.get("BUCKET", "mock-files")
COLLECTION = os.environ.get("COLLECTION", "jobs")
POLL_MS = int(os.environ.get("POLL_MS", "1500"))

db = firestore.Client(project=PROJECT)
gcs = storage.Client(project=PROJECT)


def process(doc_id, data):
    file_meta = data.get("file") or {}
    bucket_name = file_meta.get("bucket") or BUCKET
    path = file_meta.get("path")
    if not path:
        raise ValueError("document has no file.path")

    blob = gcs.bucket(bucket_name).blob(path)
    raw = blob.download_as_bytes()
    preview = raw[:200].decode("utf-8", errors="replace")
    return {"bytes": len(raw), "preview": preview}


def tick():
    pending = (
        db.collection(COLLECTION)
        .where(filter=FieldFilter("status", "==", "queued"))
        .limit(5)
        .stream()
    )
    for snap in pending:
        ref = snap.reference
        data = snap.to_dict()
        ref.update(
            {
                "status": "running",
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            }
        )
        try:
            result = process(snap.id, data)
            ref.update(
                {
                    "status": "done",
                    "result": result,
                    "error": None,
                    "updatedAt": datetime.now(timezone.utc).isoformat(),
                }
            )
            print(f"done {snap.id} bytes={result['bytes']}", flush=True)
        except Exception as e:
            ref.update(
                {
                    "status": "failed",
                    "error": str(e),
                    "updatedAt": datetime.now(timezone.utc).isoformat(),
                }
            )
            print(f"failed {snap.id}: {e}", flush=True)


def main():
    print("worker polling", COLLECTION, flush=True)
    while True:
        try:
            tick()
        except Exception as e:
            print("tick error:", e, flush=True)
        time.sleep(POLL_MS / 1000)


if __name__ == "__main__":
    main()
