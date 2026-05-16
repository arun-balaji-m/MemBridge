"""
routers/index.py — MemoryBridge Phase 2
GET /index?key=<session_key>
Returns full topic index with retrieved/remaining counts.
"""

import asyncio
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from api.services.session_service import resolve_session
from api.utils.vectorstore import get_db, get_all_summaries, get_counts
from api.models.response_models import IndexResponse, TopicItem

router = APIRouter()


@router.get("/index", response_model=IndexResponse)
async def get_index(
    key: str,
    authorization: Optional[str] = Header(None, description="Bearer <google_access_token> (only needed first time)"),
):
    token = _extract_token(authorization)
    entry = await resolve_session(key, token)

    loop = asyncio.get_event_loop()

    def _read():
        with get_db(entry.db_path) as conn:
            summaries = get_all_summaries(conn)
            counts    = get_counts(conn)
        return summaries, counts

    summaries, counts = await loop.run_in_executor(None, _read)

    topics = [
        TopicItem(
            id=s["id"],
            title=s["title"],
            category=s["category"],
            retrieved=s["retrieved"],
        )
        for s in summaries
    ]

    return IndexResponse(
        project=entry.metadata.get("project_name", key),
        source_url=entry.metadata.get("source_url", ""),
        total_chunks=counts["total"],
        retrieved=counts["retrieved"],
        remaining=counts["remaining"],
        topics=topics,
    )


def _extract_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authorization header must be 'Bearer <token>'",
        )
    return authorization[len("Bearer "):]
