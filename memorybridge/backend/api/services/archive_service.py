"""
services/archive_service.py — MemoryBridge Phase 2
Orchestrates the archive flow:
  1. Sync latest DB back to Drive
  2. Move ZIP to MemoryBridge/archive/ folder
  3. Invalidate cache + clean /tmp
"""

import asyncio
import logging
from datetime import datetime, timezone

from api.services.drive_service import update_package, move_to_archive
from api.utils.cache import cache_invalidate, _CacheEntry

log = logging.getLogger(__name__)


async def run_archive(entry: _CacheEntry) -> str:
    """
    Archive a session. Returns ISO timestamp of archival.
    Safe to call multiple times — idempotent on Drive side.
    """
    loop = asyncio.get_event_loop()

    # 1. Sync latest DB to Drive before moving
    try:
        await loop.run_in_executor(
            None,
            update_package,
            entry.access_token,
            entry.drive_file_id,
            entry.db_path,
        )
        log.info("Archive: DB synced for key=%s", entry.session_key)
    except Exception as exc:
        log.warning("Archive: DB sync failed for key=%s: %s — continuing", entry.session_key, exc)

    # 2. Move ZIP to archive folder in Drive
    await loop.run_in_executor(
        None,
        move_to_archive,
        entry.access_token,
        entry.drive_file_id,
    )
    log.info("Archive: moved to archive/ key=%s", entry.session_key)

    # 3. Invalidate local cache + clean /tmp
    cache_invalidate(entry.session_key)

    archived_at = datetime.now(timezone.utc).isoformat()
    log.info("Archive complete key=%s at=%s", entry.session_key, archived_at)
    return archived_at
