# MyAstroShine backend - FastAPI + OpenCV
FROM python:3.14-slim

WORKDIR /app

# System dependencies for OpenCV runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY alembic.ini .
COPY migrations/ migrations/

# Single persistence root; the app creates the subtree (db/, images/, stacks/,
# cache/) and secret_key.txt / app_settings.json at startup.
ENV DATA_DIR=/data
RUN mkdir -p /data

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8002/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
