# email-service — orchestrator + mail transport. No model library: everything here is
# deterministic (intake, transport, orchestration, delivery). The editor service is the
# only thing that calls a model.
#
# Build from the repo root so the uv workspace (root pyproject.toml + uv.lock) and this
# service's workspace dependencies (mff-contracts, mff-docmodel, mff-store, mff-applier)
# are all in the build context:
#
#   docker build -f docker/email-service.Dockerfile -t mff/email-service .
#
# Multi-stage: `builder` resolves and installs with uv into a venv that is not editable,
# so `runtime` needs nothing but that venv — no source tree, no uv, no wheel cache.

# ---------------------------------------------------------------------------------------
# builder
# ---------------------------------------------------------------------------------------
FROM python:3.12-slim AS builder

# Pin uv to the same version CI uses (.github/workflows/ci.yml), copied in rather than
# pip-installed so it never touches the final image at all.
COPY --from=ghcr.io/astral-sh/uv:0.7.14 /uv /uvx /bin/

ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Workspace root first — the lockfile is what makes this reproducible.
COPY pyproject.toml uv.lock ./
# Every workspace member: uv needs their pyproject.toml to resolve, even the ones this
# service does not depend on. --package below still installs only this service's closure.
COPY packages packages
COPY services services

# Cache mount, not a layer: BuildKit keeps it outside the image entirely, which is what
# "wheel cache not shipped" means in practice — there is nothing to prune afterwards.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package email-service

# --- Architecture guard -----------------------------------------------------------------
# An agent framework belongs to the editor service only. If one shows up here, something
# has moved to the wrong side of the "only the editor calls a model" line and the build
# should fail loudly rather than ship a quietly drifted image.
#
# Both names are checked: google-adk is what the editor uses now, and pydantic-ai is
# banned because pydantic-evals pins pydantic-ai-slim -- it is importable in the dev
# environment, so only an explicit check stops it drifting into a service image.
RUN set -eu; \
    deps="$(uv pip list --python "$UV_PROJECT_ENVIRONMENT/bin/python")"; \
    echo "$deps"; \
    for banned in google-adk pydantic-ai; do \
        if echo "$deps" | grep -iq "^$banned"; then \
            echo "ARCHITECTURE DRIFT: $banned must not appear in email-service." >&2; \
            echo "The editor service is the only thing that calls a model." >&2; \
            exit 1; \
        fi; \
    done

# ---------------------------------------------------------------------------------------
# runtime
# ---------------------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Fixed uid, shared across every image in this repo — never root.
RUN useradd --create-home --uid 10001 --user-group app

COPY --from=builder /app/.venv /app/.venv

USER app

EXPOSE 8000

# No curl in slim; urllib is stdlib and needs nothing extra.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz').status==200 else 1)"

# email_service.main:app is the documented entrypoint shape (docs/app-implementation-plan.md,
# "Service structure") and lands with B3/B4/B5/B13. Until then this image builds cleanly
# but the module does not exist yet — see docker's own README for what that means today.
CMD ["uvicorn", "email_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
