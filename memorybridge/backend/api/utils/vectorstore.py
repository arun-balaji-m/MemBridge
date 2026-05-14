"""
utils/vectorstore.py — MemoryBridge Phase 2
Ported from Phase 1 backend/vectorstore.py with a per-request
get_db() context manager added for thread-safe async use.
"""

import sqlite3
import json
import sqlite_vec
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional


# ── Per-request connection context manager ───────────────────────────────────

@contextmanager
def get_db(db_path: str):
    """
    Open a SQLite connection with sqlite-vec loaded, yield it, then close.
    Always use this in FastAPI endpoints via run_in_executor — never share
    connections across threads.
    """
    conn = _connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


# ── Connection helper ────────────────────────────────────────────────────────

def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
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
    tags        TEXT,
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
    conn = _connect(db_path)
    conn.execute(SCHEMA_CHUNKS)
    conn.execute(SCHEMA_VEC)
    conn.commit()
    return conn


# ── Write operations ─────────────────────────────────────────────────────────

def store_chunk(conn: sqlite3.Connection, chunk: dict, vector: list[float]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    tags_json = json.dumps(chunk.get("tags", []))
    conn.execute(
        """
        INSERT OR REPLACE INTO chunks
            (id, title, summary, detail, code, tags, category, retrieved, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chunk["id"], chunk["title"], chunk["summary"], chunk["detail"],
            chunk.get("code"), tags_json, chunk["category"],
            int(chunk.get("retrieved", False)), now,
        ),
    )
    conn.execute(
        "INSERT OR REPLACE INTO vec_chunks (chunk_id, embedding) VALUES (?, ?)",
        (chunk["id"], json.dumps(vector)),
    )
    conn.commit()


def mark_retrieved(conn: sqlite3.Connection, chunk_id: str) -> None:
    conn.execute("UPDATE chunks SET retrieved = 1 WHERE id = ?", (chunk_id,))
    conn.commit()


def mark_retrieved_bulk(conn: sqlite3.Connection, chunk_ids: list[str]) -> None:
    placeholders = ",".join("?" * len(chunk_ids))
    conn.execute(
        f"UPDATE chunks SET retrieved = 1 WHERE id IN ({placeholders})", chunk_ids
    )
    conn.commit()


# ── Read operations ──────────────────────────────────────────────────────────

def search(
    conn: sqlite3.Connection,
    query_vector: list[float],
    top_k: int = 3,
) -> list[dict]:
    vec_json = json.dumps(query_vector)
    rows = conn.execute(
        """
        SELECT v.chunk_id, vec_distance_cosine(v.embedding, ?) AS distance
        FROM vec_chunks v
        ORDER BY distance
        LIMIT ?
        """,
        (vec_json, top_k * 2),
    ).fetchall()

    results = []
    for row in rows:
        chunk = conn.execute(
            "SELECT * FROM chunks WHERE id = ?", (row["chunk_id"],)
        ).fetchone()
        if chunk is None:
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
            "similarity_score": round(1.0 - float(row["distance"]), 4),
        })
        if len(results) >= top_k:
            break
    return results


def get_all_summaries(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, title, summary, tags, category, retrieved FROM chunks ORDER BY rowid"
    ).fetchall()
    return [
        {
            "id": r["id"],
            "title": r["title"],
            "summary": r["summary"],
            "tags": json.loads(r["tags"] or "[]"),
            "category": r["category"],
            "retrieved": bool(r["retrieved"]),
        }
        for r in rows
    ]


def get_counts(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        "SELECT COUNT(*) AS total, SUM(retrieved) AS done FROM chunks"
    ).fetchone()
    total = row["total"] or 0
    done = int(row["done"] or 0)
    return {"total": total, "retrieved": done, "remaining": total - done}


def check_complete(conn: sqlite3.Connection) -> bool:
    counts = get_counts(conn)
    return counts["total"] > 0 and counts["remaining"] == 0
