# API image. Runs as a non-root user and builds the Qdrant index at build time,
# so the container starts with search ready.
FROM python:3.11-slim

RUN useradd -m -u 1000 app
USER app
ENV PATH="/home/app/.local/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    HF_HUB_DISABLE_SYMLINKS_WARNING=1
WORKDIR /home/app/api

COPY --chown=app requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=app app ./app
COPY --chown=app scripts ./scripts
COPY --chown=app data/catalog.jsonl data/orders.json ./data/
COPY --chown=app data/policies ./data/policies
RUN python scripts/build_index.py

# One worker: embedded Qdrant allows a single process (use QDRANT_URL to scale out).
# Hosts like Render pass the port in $PORT; 7860 is the local default.
EXPOSE 7860
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
