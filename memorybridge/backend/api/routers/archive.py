"""
routers/archive.py — MemoryBridge Phase 2
POST /archive?key=<session_key>
Manually triggers archive — moves package to Drive archive folder,
clears cache and /tmp.
"""

from fastapi import APIRouter, Header, HTTPException
from api.services.session_service import resolve_session
from api.services.archive_service import run_archive
from api.models.response_models import ArchiveResponse

router = APIRouter()


@router.post("/archive", response_model=ArchiveResponse)
async def archive_memory(
    key: str,
    authorization: str = Header(..., description="Bearer <google_access_token>"),
):
    token = _extract_token(authorization)
    entry = await resolve_session(key, token)

    if entry.archiving:
        raise HTTPException(
            status_code=409,
            detail="Archive already in progress for this session.",
        )

    entry.archiving = True
    try:
        archived_at = await run_archive(entry)
    except Exception as exc:
        entry.archiving = False
        raise HTTPException(
            status_code=500,
            detail=f"Archive failed: {exc}",
        )

    return ArchiveResponse(
        status="archived",
        project=entry.metadata.get("project_name", key),
        archived_at=archived_at,
    )


def _extract_token(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authorization header must be 'Bearer <token>'",
        )
    return authorization[len("Bearer "):]
