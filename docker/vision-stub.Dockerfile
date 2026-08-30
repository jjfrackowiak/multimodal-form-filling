# vision-stub — placeholder for image understanding (req 13, owned separately per
# AGENTS.md). Real and working, unlike its two siblings: answers from the fleet fixture's
# labelled inventory and processes no pixels. Replaced wholesale when the real vision
# service lands — the image name and port are the only things the editor depends on.
#
#   docker build -f docker/vision-stub.Dockerfile -t mff/vision-stub .
#
# Same shape as email-service.Dockerfile / editor-service.Dockerfile, with one addition:
# it is the sole image allowed to carry any part of fixtures/ — one file, copied by
# explicit path, which is the clearest marker of what makes this service a placeholder.

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
    uv sync --frozen --no-dev --no-editable --package vision-stub

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

# The one exception to "fixtures/ ships in no production image": the stand-in reads its
# labels from here. Copied by explicit single-file path — never `COPY fixtures/`, which
# would drag in the other 12 MB of photographs this service has no use for.
COPY fixtures/fleet-vehicle-return/inventory.yaml /app/fixtures/fleet-vehicle-return/inventory.yaml
ENV MFF_VISION_INVENTORY=/app/fixtures/fleet-vehicle-return/inventory.yaml

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz').status==200 else 1)"

CMD ["uvicorn", "vision_stub.main:app", "--host", "0.0.0.0", "--port", "8000"]
