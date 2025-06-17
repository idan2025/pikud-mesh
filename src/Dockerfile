# ---------- Dockerfile ----------
FROM python:3.12-slim

ENV PIP_NO_CACHE_DIR=1
ENV PYTHONIOENCODING=UTF-8
ENV TZ=Asia/Jerusalem

RUN apt-get update && apt-get install -y tzdata && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir meshtastic requests feedparser

COPY bridge.py /app/bridge.py
WORKDIR /app
ENTRYPOINT ["python", "bridge.py"]
# ---------------------------------
