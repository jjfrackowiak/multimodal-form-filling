FROM python:3.12-slim
WORKDIR /app
RUN useradd --create-home --uid 10001 app
COPY cv/requirements.txt /app/cv/requirements.txt
RUN pip install --no-cache-dir -r /app/cv/requirements.txt
COPY cv /app/cv
ENV PORT=8080 PYTHONUNBUFFERED=1
USER app
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')"
CMD ["sh", "-c", "exec uvicorn cv.service:app --host 0.0.0.0 --port ${PORT} --timeout-keep-alive 30"]
