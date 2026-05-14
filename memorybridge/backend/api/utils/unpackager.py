"""
utils/unpackager.py — MemoryBridge Phase 2
Extracts a memory ZIP package downloaded from Google Drive
into a temp directory. Returns paths to the extracted files.
"""

import zipfile
import io
import json
from pathlib import Path


def unpack(zip_bytes: bytes, dest_dir: str) -> dict:
    """
    Extract memory.db, index.json, metadata.json from zip_bytes
    into dest_dir. Returns dict with file paths and parsed metadata.

    Args:
        zip_bytes: raw ZIP content from Drive download
        dest_dir:  destination directory (created if needed)

    Returns:
        {
            "db_path": str,
            "index_path": str,
            "metadata_path": str,
            "metadata": dict,
        }
    """
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        zf.extractall(dest)

    db_path       = str(dest / "memory.db")
    index_path    = str(dest / "index.json")
    metadata_path = str(dest / "metadata.json")

    # Validate expected files exist
    for path in (db_path, metadata_path):
        if not Path(path).exists():
            raise ValueError(
                f"Invalid memory package — missing {Path(path).name}. "
                "Re-extract the conversation using the Chrome extension."
            )

    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    return {
        "db_path": db_path,
        "index_path": index_path,
        "metadata_path": metadata_path,
        "metadata": metadata,
    }
