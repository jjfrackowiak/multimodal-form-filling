import os

from flask import Flask, jsonify

PORT = int(os.environ.get("PORT", "8080"))
app = Flask(__name__)


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "editor",
        "owner": "Janek",
        "status": "stub",
    }


@app.post("/runs")
def runs():
    return jsonify(
        {
            "error": "not implemented",
            "service": "editor",
            "hint": "Janek: scoped agent run, line edits, comments, Pydantic retry",
        }
    ), 501


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
