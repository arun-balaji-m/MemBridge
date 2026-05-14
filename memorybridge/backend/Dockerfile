# ─────────────────────────────────────────────────────────────────────────────
# MemoryBridge — Combined Dockerfile (Phase 1 + Phase 2)
# supervisord runs both:
#   Phase 1: Flask embedder  on port 8765 (internal)
#   Phase 2: FastAPI API     on port 8000 (public — Railway routes here)
# Extension calls /embed on the public URL; Phase 2 proxies to Phase 1 internally.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Install supervisor
RUN apt-get update \
    && apt-get install -y --no-install-recommends supervisor \
    && rm -rf /var/lib/apt/lists/*

# CPU-only torch first (saves ~1.5 GB of CUDA packages)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Combined requirements (Phase 1 + Phase 2)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake model into image layer — eliminates cold-start download
RUN python -c "from sentence_transformers import SentenceTransformer; \
               SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

# Copy all application code
COPY embedder.py vectorstore.py packager.py ./
COPY api/ ./api/

# /tmp is writable on Railway — SQLite packages extracted here at runtime
RUN mkdir -p /tmp/memorybridge

# Supervisor config
COPY supervisord.conf /etc/supervisor/conf.d/memorybridge.conf

# Both ports documented (Railway only exposes 8000 publicly)
EXPOSE 8765 8000

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# supervisord starts both Phase 1 (port 8765) and Phase 2 (port 8000)
CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/conf.d/memorybridge.conf"]
