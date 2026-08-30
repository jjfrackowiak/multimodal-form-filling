# Placeholder vision service. Replaced wholesale when the real one lands —
# the image name and the port are the only things the editor depends on.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY packages/mff-vision /app/packages/mff-vision
COPY services/vision-stub /app/services/vision-stub

RUN pip install --no-cache-dir ./packages/mff-vision ./services/vision-stub \
 && useradd --create-home --uid 10001 app

# The mock answers from the fixture, so the fixture has to be in the image.
# The real service will not need this line — it is the clearest single marker
# of what makes this a placeholder.
COPY fixtures/fleet-vehicle-return/inventory.yaml /app/fixtures/fleet-vehicle-return/inventory.yaml
ENV MFF_VISION_INVENTORY=/app/fixtures/fleet-vehicle-return/inventory.yaml

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz').status==200 else 1)"

CMD ["uvicorn", "vision_stub.main:app", "--host", "0.0.0.0", "--port", "8000"]
