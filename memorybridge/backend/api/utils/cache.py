"""
utils/cache.py — MemoryBridge Phase 2
In-memory TTL cache for downloaded memory packages.
Each cache entry holds the local db_path, metadata, and a per-session
write lock so concurrent mark_retrieved writes are serialized.
"""

import time
import asyncio
import threading
import shutil
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_cache: dict[str, "_CacheEntry"] = {}
_cache_lock = threading.Lock()


@dataclass
class _CacheEntry:
    session_key: str
    db_path: str
    metadata: dict
    drive_file_id: str
    access_token: str          # most recent token — used for end-of-TTL sync
    last_accessed: float = field(default_factory=time.monotonic)
    expires_at: float = field(default_factory=time.monotonic)
    write_lock: threading.Lock = field(default_factory=threading.Lock)
    archiving: bool = False    # guard against concurrent archive triggers


# ── Public API ────────────────────────────────────────────────────────────────

def cache_get(key: str) -> Optional[_CacheEntry]:
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        if time.monotonic() > entry.expires_at:
            # Expired — remove but let background task do the Drive sync
            return None
        entry.last_accessed = time.monotonic()
        return entry


def cache_set(
    key: str,
    db_path: str,
    metadata: dict,
    drive_file_id: str,
    access_token: str,
    ttl: float = 3600.0,
) -> _CacheEntry:
    entry = _CacheEntry(
        session_key=key,
        db_path=db_path,
        metadata=metadata,
        drive_file_id=drive_file_id,
        access_token=access_token,
        last_accessed=time.monotonic(),
        expires_at=time.monotonic() + ttl,
    )
    with _cache_lock:
        _cache[key] = entry
    log.info("Cache SET key=%s ttl=%.0fs", key, ttl)
    return entry


def cache_update_token(key: str, access_token: str) -> None:
    """Refresh the stored token for an existing cache entry."""
    with _cache_lock:
        if key in _cache:
            _cache[key].access_token = access_token


def cache_invalidate(key: str) -> None:
    """Remove a session from cache and delete its /tmp directory."""
    with _cache_lock:
        entry = _cache.pop(key, None)
    if entry:
        _cleanup_tmp(entry.db_path)
        log.info("Cache INVALIDATED key=%s", key)


def cache_get_all_keys() -> list[str]:
    with _cache_lock:
        return list(_cache.keys())


# ── Background eviction ───────────────────────────────────────────────────────

async def eviction_loop(ttl: float = 3600.0) -> None:
    """
    Runs forever as an asyncio background task.
    Every 60 s: finds expired entries, syncs their DB back to Drive,
    then clears them from cache and /tmp.
    """
    # Import here to avoid circular import at module level
    from api.services.drive_service import update_package  # noqa: PLC0415

    while True:
        await asyncio.sleep(60)
        now = time.monotonic()

        with _cache_lock:
            expired = [e for e in _cache.values() if now > e.expires_at]

        for entry in expired:
            log.info("Cache EXPIRE key=%s — syncing to Drive", entry.session_key)
            try:
                # Run the blocking Drive upload in a thread
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda e=entry: update_package(
                        e.access_token, e.drive_file_id, e.db_path
                    ),
                )
            except Exception as exc:
                log.warning("Drive sync on evict failed for %s: %s", entry.session_key, exc)

            with _cache_lock:
                _cache.pop(entry.session_key, None)

            _cleanup_tmp(entry.db_path)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cleanup_tmp(db_path: str) -> None:
    try:
        session_dir = Path(db_path).parent
        if session_dir.exists() and str(session_dir).startswith("/tmp/"):
            shutil.rmtree(session_dir, ignore_errors=True)
    except Exception as exc:
        log.warning("Cleanup failed for %s: %s", db_path, exc)
