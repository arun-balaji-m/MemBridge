# ─────────────────────────────────────────────────────────────────────────────
# MemoryBridge — Combined Dockerfile (Phase 1 + Phase 2)
# ─────────────────────────────────────────────────────────────────────────────
 
FROM python:3.11-slim
 
WORKDIR /app
 
# Install supervisor
RUN apt-get update \
&& apt-get install -y --no-install-recommends supervisor \
&& rm -rf /var/lib/apt/lists/*
 
# Install CPU-only PyTorch
RUN pip install --no-cache-dir torch \
    --index-url https://download.pytorch.org/whl/cpu
 
# Copy requirements from repo root path
COPY memorybridge/backend/requirements.txt ./requirements.txt
 
# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt
 
# Pre-download embedding model
# If Railway fails here due to memory/time limits,
# comment this block temporarily.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
 
# Copy backend source files from repo root path
COPY memorybridge/backend/embedder.py ./embedder.py
COPY memorybridge/backend/vectorstore.py ./vectorstore.py
COPY memorybridge/backend/packager.py ./packager.py
 
# Copy API directory
COPY memorybridge/backend/api ./api
 
# Create writable temp directory
RUN mkdir -p /tmp/memorybridge
 
# Copy supervisor config from repo root path
COPY memorybridge/backend/supervisord.conf /etc/supervisor/conf.d/memorybridge.conf
 
# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
 
# Expose ports
EXPOSE 8000
EXPOSE 8765
 
# Start services
CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/conf.d/memorybridge.conf"]