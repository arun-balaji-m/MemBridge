"""
routers/query.py — MemoryBridge Phase 2
GET /query?key=<key>&question=<text>&top_k=3
Embeds the question, runs vector search, marks chunks retrieved,
auto-archives if all chunks have been retrieved.
"""

import asyncio
from fastapi import APIRouter, Header, HTTPException
from api.services.session_service import resolve_session
from api.services.embedding_service import embed_text
from api.services.archive_service import run_archive
from api.utils.vectorstore import get_db, search, mark_retrieved_bulk, get_counts, check_complete
from api.models.response_models import QueryResponse, ChunkResult
from api.state import app_state

router = APIRouter()


@router.get("/query", response_model=QueryResponse)
async def query_memory(
    key: str,
    question: str,
    top_k: int = 3,
    authorization: str = Header(..., description="Bearer <google_access_token>"),
):
    token = _extract_token(authorization)

    if not question.strip():
        raise HTTPException(status_code=400, detail="'question' must not be empty.")
    if not (1 <= top_k <= 10):
        raise HTTPException(status_code=400, detail="'top_k' must be between 1 and 10.")

    entry = await resolve_session(key, token)

    # Guard: already archiving
    if entry.archiving:
        raise HTTPException(
            status_code=410,
            detail={
                "error": "already_archived",
                "message": "All context has been retrieved and this memory is being archived.",
            },
        )

    # 1. Embed the question
    question_vector = await embed_text(app_state, question)

    # 2. Vector search + mark retrieved (sync, in thread)
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

    # 3. Build response
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

    # 4. Auto-archive if all retrieved
    if complete and not entry.archiving:
        entry.archiving = True  # set flag before await to prevent race
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


def _extract_token(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authorization header must be 'Bearer <token>'",
        )
    return authorization[len("Bearer "):]
