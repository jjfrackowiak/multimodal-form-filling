# Real vision service. Build from repo root:
#   gcloud builds submit --tag "$IMG" -f services/cv/Dockerfile .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app
RUN useradd --create-home --uid 10001 app

COPY services/cv /app/services/cv
RUN pip install --no-cache-dir /app/services/cv

USER app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')"

CMD ["sh", "-c", "exec uvicorn cv.service:app --host 0.0.0.0 --port ${PORT} --timeout-keep-alive 30"]
