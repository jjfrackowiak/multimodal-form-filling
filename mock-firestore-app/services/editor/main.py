import os

from flask import Flask, jsonify

PORT = int(os.environ.get("PORT", "8080"))
CV_URL = os.environ.get("CV_URL", "")
app = Flask(__name__)


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "editor",
        "owner": "Janek",
        "status": "stub",
        "cv_url": CV_URL or None,
    }


@app.post("/runs")
def runs():
    # When filling this in: POST {CV_URL}/v1/inventory (see cv/integration_guide_CV.md).
    # Do not put Vertex / cropping in this service.
    return jsonify(
        {
            "error": "not implemented",
            "service": "editor",
            "hint": "Janek: scoped agent run, line edits, comments, Pydantic retry",
            "cv_tool": f"POST {CV_URL}/v1/inventory" if CV_URL else None,
        }
    ), 501


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
