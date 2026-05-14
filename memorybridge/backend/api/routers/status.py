"""
routers/status.py — MemoryBridge Phase 2
GET /status?key=<session_key>
Returns retrieval progress.
"""

import asyncio
from fastapi import APIRouter, Header, HTTPException
from api.services.session_service import resolve_session
from api.utils.vectorstore import get_db, get_counts
from api.models.response_models import StatusResponse

router = APIRouter()


@router.get("/status", response_model=StatusResponse)
async def get_status(
    key: str,
    authorization: str = Header(..., description="Bearer <google_access_token>"),
):
    token = _extract_token(authorization)
    entry = await resolve_session(key, token)

    loop = asyncio.get_event_loop()

    def _read():
        with get_db(entry.db_path) as conn:
            return get_counts(conn)

    counts = await loop.run_in_executor(None, _read)

    total = counts["total"]
    done  = counts["retrieved"]
    pct   = round((done / total) * 100) if total > 0 else 0

    status = "active"
    if entry.archiving:
        status = "archiving"
    elif total > 0 and done == total:
        status = "complete"

    return StatusResponse(
        project=entry.metadata.get("project_name", key),
        total_chunks=total,
        retrieved=done,
        remaining=counts["remaining"],
        percent_complete=pct,
        status=status,
    )


def _extract_token(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authorization header must be 'Bearer <token>'",
        )
    return authorization[len("Bearer "):]
