"""
routers/query.py — MemoryBridge Phase 2

GET  /query?key=<key>&question=<text>&top_k=3
POST /query  {"key": "...", "question": "...", "top_k": 3}

POST is preferred for LLM use — avoids 422 URL encoding errors
with spaces and special characters in the question text.
"""

import asyncio
import logging
from urllib.parse import unquote_plus
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel
from api.services.session_service import resolve_session
from api.services.embedding_service import embed_text
from api.services.archive_service import run_archive
from api.utils.vectorstore import get_db, search, mark_retrieved_bulk, get_counts, check_complete
from api.models.response_models import QueryResponse, ChunkResult
from api.state import app_state

log = logging.getLogger(__name__)

router = APIRouter()


class QueryBody(BaseModel):
    key: str
    question: str
    top_k: int = 3


# ── Shared logic ───────────────────────────────────────────────────────────────

async def _run_query(key: str, question: str, top_k: int, token: Optional[str]) -> QueryResponse:
    if not question.strip():
        raise HTTPException(status_code=400, detail="'question' must not be empty.")
    if not (1 <= top_k <= 10):
        raise HTTPException(status_code=400, detail="'top_k' must be between 1 and 10.")

    entry = await resolve_session(key, token)

    if entry.archiving:
        raise HTTPException(
            status_code=410,
            detail={
                "error": "already_archived",
                "message": "All context has been retrieved and this memory is being archived.",
            },
        )

    try:
        question_vector = await embed_text(app_state, question)
    except Exception as exc:
        log.exception("Embedding failed for question=%r", question)
        raise HTTPException(status_code=500, detail=f"Embedding failed: {exc}")
    loop = asyncio.get_event_loop()

    def _search_and_mark():
        with entry.write_lock:
            with get_db(entry.db_path) as conn:
                results = search(conn, question_vector, top_k=top_k)
                ids = [r["id"] for r in results]
                if ids:
                    mark_retrieved_bulk(conn, ids)
                counts = get_counts(conn)
                complete = check_complete(conn)
        return results, counts, complete

    results, counts, complete = await loop.run_in_executor(None, _search_and_mark)

    chunks = [
        ChunkResult(
            id=r["id"],
            title=r["title"],
            summary=r["summary"],
            detail=r["detail"],
            code=r["code"],
            tags=r["tags"],
            category=r["category"],
            similarity_score=r["similarity_score"],
        )
        for r in results
    ]

    response = QueryResponse(
        chunks=chunks,
        total_returned=len(chunks),
        remaining_chunks=counts["remaining"],
    )

    if complete and not entry.archiving:
        entry.archiving = True
        try:
            await run_archive(entry)
            response.auto_archived = True
            response.message = (
                "All context has been retrieved. "
                "Memory has been auto-archived to your Google Drive."
            )
        except Exception as exc:
            entry.archiving = False
            response.message = f"Auto-archive failed: {exc}"

    return response

# ── GET /query and GET /fetch — raw param parsing to survive LLM URL encoding ──
# Uses Request directly so badly-encoded URLs don't trigger FastAPI 422.

def _parse_get_params(request: Request):
    """Manually extract key, question, top_k from raw query string."""
    raw = str(request.url.query)  # raw undecoded query string
    params = {}
    for part in raw.split("&"):
        if "=" in part:
            k, _, v = part.partition("=")
            params[unquote_plus(k)] = unquote_plus(v)
        elif part:
            params[unquote_plus(part)] = ""

    key = params.get("key", "").strip()
    question = params.get("question", params.get("q", "")).strip()
    try:
        top_k = int(params.get("top_k", "3"))
    except ValueError:
        top_k = 3

    if not key:
        raise HTTPException(status_code=422, detail="Missing required parameter: 'key'")
    if not question:
        raise HTTPException(status_code=422, detail="Missing required parameter: 'question' (or 'q')")

    return key, question, top_k


@router.get("/query")
async def query_memory_get(request: Request, authorization: Optional[str] = Header(None)):
    key, question, top_k = _parse_get_params(request)
    return await _run_query(key, question, top_k, _extract_token(authorization))


@router.get("/fetch")
async def fetch_memory_get(request: Request, authorization: Optional[str] = Header(None)):
    """Alias for GET /query — use ?q= as shorter param to avoid encoding issues."""
    key, question, top_k = _parse_get_params(request)
    return await _run_query(key, question, top_k, _extract_token(authorization))


# ── POST endpoint (preferred for function-calling clients) ────────────────────

@router.post("/query", response_model=QueryResponse)
async def query_memory_post(
    body: QueryBody,
    authorization: Optional[str] = Header(None),
):
    return await _run_query(body.key, body.question, body.top_k, _extract_token(authorization))


# ── Helper ───────────────────────────────────────────────────────────────────────

def _extract_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authorization header must be 'Bearer <token>'",
        )
    return authorization[len("Bearer "):]
