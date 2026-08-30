# editor-service — the only service that calls a model. Google ADK (`google-adk`)
# lands with B8; python-docx must never appear here — the orchestrator (email-service)
# parses documents into Nodes and hands them over as data, so a document library showing
# up on this side means something has moved to the wrong service.
#
# Build from the repo root:
#
#   docker build -f docker/editor-service.Dockerfile -t mff/editor-service .
#
# Same shape as email-service.Dockerfile — see that file for the pattern's rationale.

# ---------------------------------------------------------------------------------------
# builder
# ---------------------------------------------------------------------------------------
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.7.14 /uv /uvx /bin/

ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY packages packages
COPY services services

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package editor-service

# --- Architecture guard -----------------------------------------------------------------
# python-docx belongs to mff-docmodel / email-service only. If it shows up here, the
# editor has started touching .docx bytes directly instead of the Node data the
# orchestrator hands it, and the build should fail loudly rather than ship the drift.
RUN set -eu; \
    deps="$(uv pip list --python "$UV_PROJECT_ENVIRONMENT/bin/python")"; \
    echo "$deps"; \
    if echo "$deps" | grep -iq '^python-docx'; then \
        echo "ARCHITECTURE DRIFT: python-docx must not appear in editor-service." >&2; \
        echo "The email service owns document parsing; the editor works on Nodes." >&2; \
        exit 1; \
    fi

# ---------------------------------------------------------------------------------------
# runtime
# ---------------------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN useradd --create-home --uid 10001 --user-group app

COPY --from=builder /app/.venv /app/.venv

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz').status==200 else 1)"

# editor_service.main:app + POST /slices:run + GET /healthz land with B8, which is also
# where fastapi/uvicorn become this service's dependencies. Until then the image builds
# (the venv today has only mff-contracts in it) but this CMD has nothing to exec — see
# docker/README.md.
CMD ["uvicorn", "editor_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
