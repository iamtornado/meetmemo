FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    gcc \
    g++ \
    make \
    git \
    && rm -rf /var/lib/apt/lists/*

# Use Tsinghua mirror for pip (China-friendly)
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

COPY requirements.txt .
RUN pip install --default-timeout=300 --no-cache-dir -r requirements.txt

COPY main.py .

ENV HOST=0.0.0.0
ENV PORT=8001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
