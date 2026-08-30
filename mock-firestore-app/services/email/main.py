import os

from flask import Flask, jsonify

PORT = int(os.environ.get("PORT", "8080"))
app = Flask(__name__)


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "email",
        "owner": "Janek",
        "status": "stub",
    }


@app.post("/inbound")
def inbound():
    return jsonify(
        {
            "error": "not implemented",
            "service": "email",
            "hint": "Janek: intake email, validate attachments/manifest, create job via api /files",
        }
    ), 501


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
