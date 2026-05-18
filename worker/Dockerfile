FROM python:3.11-slim

WORKDIR /app

# Install system deps (including CUDA-related for GPU)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    gcc \
    g++ \
    make \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements (backend + worker)
COPY backend/requirements.txt /tmp/backend-requirements.txt
COPY worker/requirements.txt /tmp/worker-requirements.txt
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip install --default-timeout=300 --no-cache-dir -r /tmp/backend-requirements.txt -r /tmp/worker-requirements.txt

COPY backend/app /app/app

ENV PYTHONPATH=/app
ENV WHISPER_DEVICE=cpu

# Celery worker entrypoint
CMD ["celery", "-A", "app.tasks.celery_app", "worker", "--loglevel=info", "--concurrency=1"]
