# cv — real image understanding (req 13). Vertex Gemini over ADC. No fixture lookup.
#
# Build from the repo root:
#
#   docker build -f docker/cv.Dockerfile -t mff/cv .
#
# Cloud Run injects PORT (8080). Same uv multi-stage shape as the other service images.

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
    uv sync --frozen --no-dev --no-editable --package cv

# ---------------------------------------------------------------------------------------
# runtime
# ---------------------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PORT=8080

WORKDIR /app

RUN useradd --create-home --uid 10001 --user-group app

COPY --from=builder /app/.venv /app/.venv

USER app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import os,urllib.request,sys; p=os.environ.get('PORT','8080'); sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{p}/healthz').status==200 else 1)"

CMD ["sh", "-c", "exec uvicorn cv.service:app --host 0.0.0.0 --port ${PORT}"]
