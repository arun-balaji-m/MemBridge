"""
services/session_service.py — MemoryBridge Phase 2
Central orchestration: validate token → check cache → download from
Drive on miss → unpack → populate cache → return CacheEntry.

All callers (routers) use resolve_session() as their single entry point.
"""

import asyncio
import logging
import os

from fastapi import HTTPException

from api.services.drive_service import (
    validate_token,
    find_package,
    download_package,
)
from api.utils.unpackager import unpack
from api.utils.cache import (
    cache_get,
    cache_set,
    cache_update_token,
    _CacheEntry,
)

log = logging.getLogger(__name__)

TMP_ROOT = "/tmp/memorybridge"


async def resolve_session(key: str, access_token: str | None = None) -> _CacheEntry:
    """
    Given a session key and an optional Drive access token:
      - If session is cached: return it immediately (no token needed).
        This is the normal path for LLM calls — the session was pre-warmed
        when the user clicked 'Get LLM Prompt' in the extension.
      - If not cached and token provided: download from Drive, unpack, cache.
      - If not cached and no token: return 401 with instructions.

    Raises HTTPException on any failure so routers stay clean.
    """
    loop = asyncio.get_event_loop()

    # ── 1. Check cache first (works without a token) ───────────────────────
    entry = cache_get(key)
    if entry is not None:
        if access_token:
            cache_update_token(key, access_token)
        log.debug("Cache HIT key=%s", key)
        return entry

    # ── 2. Cache miss — need a token to download from Drive ────────────────
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "session_not_initialized",
                "message": (
                    f"Session '{key}' is not loaded. "
                    "Open the MemoryBridge Chrome extension, find this session key, "
                    "and click 'Get LLM Prompt' to initialize the session. "
                    "Then paste the prompt again."
                ),
            },
        )

    # ── 3. Validate token before hitting Drive ─────────────────────────────
    token_ok = await loop.run_in_executor(None, validate_token, access_token)
    if not token_ok:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "token_expired",
                "message": (
                    "Your Google access token has expired. "
                    "Re-open the MemoryBridge Chrome extension to refresh it."
                ),
            },
        )

    log.info("Cache MISS key=%s — downloading from Drive", key)

    # ── 3. Find file on Drive ──────────────────────────────────────────────
    try:
        drive_file_id = await loop.run_in_executor(
            None, find_package, access_token, key
        )
    except Exception as exc:
        log.error("Drive search failed for key=%s: %s", key, exc)
        raise HTTPException(
            status_code=503,
            detail={
                "error": "drive_error",
                "message": f"Failed to reach Google Drive: {exc}",
            },
        )

    if drive_file_id is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "session_not_found",
                "message": (
                    f"No memory package found for session key '{key}'. "
                    "Make sure you extracted this conversation with the "
                    "MemoryBridge Chrome extension and are using the same "
                    "Google account."
                ),
            },
        )

    # ── 4. Download ZIP ────────────────────────────────────────────────────
    try:
        zip_bytes = await loop.run_in_executor(
            None, download_package, access_token, drive_file_id
        )
    except Exception as exc:
        log.error("Drive download failed for key=%s: %s", key, exc)
        raise HTTPException(
            status_code=503,
            detail={
                "error": "download_failed",
                "message": f"Failed to download memory package: {exc}",
            },
        )

    # ── 5. Unpack into /tmp ────────────────────────────────────────────────
    dest_dir = os.path.join(TMP_ROOT, key)
    try:
        unpacked = await loop.run_in_executor(None, unpack, zip_bytes, dest_dir)
    except Exception as exc:
        log.error("Unpack failed for key=%s: %s", key, exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "corrupt_package",
                "message": (
                    f"Memory package is corrupted: {exc}. "
                    "Re-extract the conversation using the Chrome extension."
                ),
            },
        )

    # ── 6. Store in cache ──────────────────────────────────────────────────
    entry = cache_set(
        key=key,
        db_path=unpacked["db_path"],
        metadata=unpacked["metadata"],
        drive_file_id=drive_file_id,
        access_token=access_token,
    )
    log.info("Session ready key=%s chunks_total=%s",
             key, unpacked["metadata"].get("total_chunks"))
    return entry
