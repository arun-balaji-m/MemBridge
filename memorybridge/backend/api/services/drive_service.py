"""
services/drive_service.py — MemoryBridge Phase 2
Google Drive API v3 operations using the user's OAuth access token
(passed on every request from the Chrome extension).

All functions accept access_token: str and build a short-lived
Credentials object — no server-side refresh token needed.
"""

import io
import hashlib
import logging
import time
from typing import Optional

import google.oauth2.credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from googleapiclient.errors import HttpError

log = logging.getLogger(__name__)

MEMORYBRIDGE_FOLDER = "MemoryBridge"
ARCHIVE_FOLDER      = "archive"

# ── Token validation cache (avoid hammering tokeninfo endpoint) ───────────────
_token_cache: dict[str, tuple[bool, float]] = {}  # hash → (valid, expires_at)


def _creds(token: str) -> google.oauth2.credentials.Credentials:
    return google.oauth2.credentials.Credentials(token=token)


def _drive(token: str):
    return build("drive", "v3", credentials=_creds(token), cache_discovery=False)


# ── Token validation ──────────────────────────────────────────────────────────

def validate_token(access_token: str) -> bool:
    """
    Check if an access token is still valid.
    Result cached for 55 minutes to avoid hammering the tokeninfo endpoint.
    """
    h = hashlib.sha256(access_token.encode()).hexdigest()
    if h in _token_cache:
        valid, expires_at = _token_cache[h]
        if time.monotonic() < expires_at:
            return valid

    import httpx
    try:
        r = httpx.get(
            "https://www.googleapis.com/oauth2/v1/tokeninfo",
            params={"access_token": access_token},
            timeout=5.0,
        )
        valid = r.status_code == 200
    except Exception:
        valid = False

    _token_cache[h] = (valid, time.monotonic() + 55 * 60)
    return valid


# ── Folder helpers ────────────────────────────────────────────────────────────

def _find_or_create_folder(service, name: str, parent_id: Optional[str] = None) -> str:
    """Return folder ID, creating it if it doesn't exist."""
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    results = service.files().list(q=query, fields="files(id,name)").execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        meta["parents"] = [parent_id]
    folder = service.files().create(body=meta, fields="id").execute()
    return folder["id"]


# ── Find session file ─────────────────────────────────────────────────────────

def find_package(access_token: str, session_key: str) -> Optional[str]:
    """
    Search for {session_key}.zip inside the MemoryBridge folder.
    Returns the Drive file ID or None if not found.
    """
    service = _drive(access_token)
    folder_id = _find_or_create_folder(service, MEMORYBRIDGE_FOLDER)

    q = (
        f"name='{session_key}.zip' "
        f"and '{folder_id}' in parents "
        f"and trashed=false"
    )
    results = service.files().list(q=q, fields="files(id,name)").execute()
    files = results.get("files", [])
    return files[0]["id"] if files else None


# ── Download ──────────────────────────────────────────────────────────────────

def download_package(access_token: str, drive_file_id: str) -> bytes:
    """Download a Drive file and return its raw bytes."""
    service = _drive(access_token)
    request = service.files().get_media(fileId=drive_file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request, chunksize=4 * 1024 * 1024)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


# ── Upload / update ───────────────────────────────────────────────────────────

def update_package(access_token: str, drive_file_id: str, db_path: str) -> None:
    """
    Re-upload only the updated memory.db content into the existing Drive ZIP.
    Because we can't partially update a ZIP, we update the file's content
    by patching the entire file. For Phase 2, we upload the raw .db file
    as a separate patch — the ZIP on Drive always reflects the Phase 1 snapshot,
    and retrieval state is the source of truth in the cached .db.

    Strategy: upload the updated db as a new version of the Drive file.
    """
    service = _drive(access_token)
    with open(db_path, "rb") as f:
        media = MediaIoBaseUpload(f, mimetype="application/octet-stream", resumable=False)
    service.files().update(fileId=drive_file_id, media_body=media).execute()
    log.info("Drive updated: file_id=%s db=%s", drive_file_id, db_path)


# ── Archive ───────────────────────────────────────────────────────────────────

def move_to_archive(access_token: str, drive_file_id: str) -> str:
    """
    Move the zip from MemoryBridge/ to MemoryBridge/archive/.
    Returns the archive folder ID.
    """
    service = _drive(access_token)

    root_folder_id    = _find_or_create_folder(service, MEMORYBRIDGE_FOLDER)
    archive_folder_id = _find_or_create_folder(service, ARCHIVE_FOLDER, parent_id=root_folder_id)

    # Get current parents
    file_meta = service.files().get(fileId=drive_file_id, fields="parents").execute()
    current_parents = ",".join(file_meta.get("parents", []))

    service.files().update(
        fileId=drive_file_id,
        addParents=archive_folder_id,
        removeParents=current_parents,
        fields="id, parents",
    ).execute()

    log.info("Moved file_id=%s → archive folder_id=%s", drive_file_id, archive_folder_id)
    return archive_folder_id
