"""
embedder.py — MemoryBridge Phase 1
Flask local server on localhost:8765.
Loads sentence-transformers all-MiniLM-L6-v2 once at startup.

Endpoints:
  POST /embed  → returns 384-dim vectors for each chunk
  POST /store  → stores chunks+vectors, packages DB, returns zip as base64
  GET  /health → liveness check
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from sentence_transformers import SentenceTransformer
import logging
import tempfile
import base64
import os
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Allow requests from Chrome extension (any origin)

# ── Load model once at startup ──────────────────────────────────────────────
log.info("Loading sentence-transformers model all-MiniLM-L6-v2 …")
MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
log.info("Model loaded. Server ready.")

MAX_CHARS = 800  # ~256 tokens; truncate detail to stay within model limit


def _build_text(chunk: dict) -> str:
    """Combine title + summary + truncated detail into one embedding string."""
    parts = [
        chunk.get("title", ""),
        chunk.get("summary", ""),
        chunk.get("detail", "")[:MAX_CHARS],
    ]
    return " ".join(p for p in parts if p).strip()


@app.post("/embed")
def embed():
    """
    Request body:
        { "chunks": [ { "id": str, "title": str, "summary": str, "detail": str }, … ] }
    Response:
        { "vectors": [ [float × 384], … ] }
    """
    body = request.get_json(force=True, silent=True)
    if not body or "chunks" not in body:
        return jsonify({"error": "Request must include a 'chunks' array."}), 400

    chunks = body["chunks"]
    if not isinstance(chunks, list) or len(chunks) == 0:
        return jsonify({"error": "'chunks' must be a non-empty array."}), 400

    texts = [_build_text(c) for c in chunks]
    log.info("Embedding %d chunk(s) …", len(texts))

    embeddings = MODEL.encode(texts, batch_size=64, show_progress_bar=False)
    vectors = [emb.tolist() for emb in embeddings]

    log.info("Done. Returning %d vector(s).", len(vectors))
    return jsonify({"vectors": vectors})


@app.post("/store")
def store():
    """
    Request body:
        {
          "chunks":       [ { chunk object } … ],
          "vectors":      [ [float × 384] … ],
          "project_name": str,
          "source_url":   str,
          "session_key":  str   (8-char)
        }
    Response:
        { "zip_base64": "<base64-encoded zip>" }
    """
    # Import here to keep startup fast and avoid circular deps
    from vectorstore import init_db, store_chunk
    from packager import create_package

    body = request.get_json(force=True, silent=True)
    if not body:
        return jsonify({"error": "Empty request body."}), 400

    chunks   = body.get("chunks", [])
    vectors  = body.get("vectors", [])
    project  = body.get("project_name", "chat")
    url      = body.get("source_url", "")
    key      = body.get("session_key", "unknown")

    if len(chunks) != len(vectors):
        return jsonify({"error": "chunks and vectors length mismatch."}), 400

    tmp_dir = tempfile.mkdtemp()
    db_path = os.path.join(tmp_dir, "memory.db")

    try:
        conn = init_db(db_path)
        for chunk, vector in zip(chunks, vectors):
            store_chunk(conn, chunk, vector)
        conn.close()

        zip_path = create_package(db_path, project, url, key, output_dir=tmp_dir)

        with open(zip_path, "rb") as f:
            zip_b64 = base64.b64encode(f.read()).decode("ascii")

        log.info("Stored %d chunks → %s.zip", len(chunks), key)
        return jsonify({"zip_base64": zip_b64})

    finally:
        # Clean up temp files
        for fname in os.listdir(tmp_dir):
            try:
                os.remove(os.path.join(tmp_dir, fname))
            except OSError:
                pass
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass


@app.get("/health")
def health():
    return jsonify({"status": "ok", "model": "all-MiniLM-L6-v2"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8765, debug=False)
