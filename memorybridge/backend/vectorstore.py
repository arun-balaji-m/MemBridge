"""
vectorstore.py — MemoryBridge Phase 1
SQLite + sqlite-vec vector storage.
Tables:
  chunks       — all chunk content and metadata
  vec_chunks   — sqlite-vec virtual table for 384-dim embeddings
"""

import sqlite3
import json
import sqlite_vec
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── Connection helper ────────────────────────────────────────────────────────

def _connect(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection with sqlite-vec extension loaded."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


# ── Schema ───────────────────────────────────────────────────────────────────

SCHEMA_CHUNKS = """
CREATE TABLE IF NOT EXISTS chunks (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    summary     TEXT NOT NULL,
    detail      TEXT NOT NULL,
    code        TEXT,
    tags        TEXT,          -- JSON array of strings
    category    TEXT NOT NULL,
    retrieved   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);
"""

SCHEMA_VEC = """
CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(
    chunk_id  TEXT PRIMARY KEY,
    embedding FLOAT[384]
);
"""


def init_db(db_path: str) -> sqlite3.Connection:
    """Create tables if they don't exist. Returns open connection."""
    conn = _connect(db_path)
    conn.execute(SCHEMA_CHUNKS)
    conn.execute(SCHEMA_VEC)
    conn.commit()
    return conn


# ── Write operations ─────────────────────────────────────────────────────────

def store_chunk(conn: sqlite3.Connection, chunk: dict, vector: list[float]) -> None:
    """
    Insert a chunk and its embedding vector.
    chunk keys: id, title, summary, detail, code, tags (list), category, retrieved
    vector: list of 384 floats
    """
    now = datetime.now(timezone.utc).isoformat()
    tags_json = json.dumps(chunk.get("tags", []))

    conn.execute(
        """
        INSERT OR REPLACE INTO chunks
            (id, title, summary, detail, code, tags, category, retrieved, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chunk["id"],
            chunk["title"],
            chunk["summary"],
            chunk["detail"],
            chunk.get("code"),
            tags_json,
            chunk["category"],
            int(chunk.get("retrieved", False)),
            now,
        ),
    )

    # sqlite-vec requires a JSON-serialised array for INSERT
    vec_json = json.dumps(vector)
    conn.execute(
        "INSERT OR REPLACE INTO vec_chunks (chunk_id, embedding) VALUES (?, ?)",
        (chunk["id"], vec_json),
    )
    conn.commit()


def mark_retrieved(conn: sqlite3.Connection, chunk_id: str) -> None:
    """Mark a chunk as retrieved so it can be excluded from future searches."""
    conn.execute("UPDATE chunks SET retrieved = 1 WHERE id = ?", (chunk_id,))
    conn.commit()


# ── Read operations ──────────────────────────────────────────────────────────

def search(
    conn: sqlite3.Connection,
    query_vector: list[float],
    top_k: int = 3,
    exclude_retrieved: bool = False,
) -> list[dict]:
    """
    Return top_k most similar chunks using cosine distance.
    Lower distance = more similar.
    """
    vec_json = json.dumps(query_vector)

    # sqlite-vec KNN with cosine distance
    rows = conn.execute(
        """
        SELECT
            v.chunk_id,
            vec_distance_cosine(v.embedding, ?) AS distance
        FROM vec_chunks v
        ORDER BY distance
        LIMIT ?
        """,
        (vec_json, top_k * 2),  # over-fetch to allow filtering
    ).fetchall()

    results = []
    for row in rows:
        chunk = conn.execute(
            "SELECT * FROM chunks WHERE id = ?", (row["chunk_id"],)
        ).fetchone()
        if chunk is None:
            continue
        if exclude_retrieved and chunk["retrieved"]:
            continue
        results.append({
            "id": chunk["id"],
            "title": chunk["title"],
            "summary": chunk["summary"],
            "detail": chunk["detail"],
            "code": chunk["code"],
            "tags": json.loads(chunk["tags"] or "[]"),
            "category": chunk["category"],
            "retrieved": bool(chunk["retrieved"]),
            "created_at": chunk["created_at"],
            "distance": row["distance"],
        })
        if len(results) >= top_k:
            break

    return results


def get_all_summaries(conn: sqlite3.Connection) -> list[dict]:
    """Return lightweight index of all chunks (for index.json)."""
    rows = conn.execute(
        "SELECT id, title, summary, tags, category FROM chunks ORDER BY rowid"
    ).fetchall()
    return [
        {
            "id": r["id"],
            "title": r["title"],
            "summary": r["summary"],
            "tags": json.loads(r["tags"] or "[]"),
            "category": r["category"],
        }
        for r in rows
    ]
