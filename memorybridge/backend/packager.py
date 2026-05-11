"""
packager.py — MemoryBridge Phase 1
Creates the final memory package:
  memory.db    — SQLite database with chunks + vectors
  index.json   — lightweight index of all chunk summaries
  metadata.json — project metadata + session key
  {session_key}.zip — the deliverable uploaded to Google Drive
"""

import json
import zipfile
import tempfile
import shutil
from datetime import datetime, timezone
from pathlib import Path

from vectorstore import get_all_summaries, _connect


def create_package(
    db_path: str,
    project_name: str,
    source_url: str,
    session_key: str,
    output_dir: str = "/tmp",
) -> str:
    """
    Build and zip the memory package.

    Args:
        db_path:      Path to the completed memory.db SQLite file.
        project_name: Human-readable project name.
        source_url:   The chat URL that was scraped.
        session_key:  8-character session key from session.js.
        output_dir:   Directory to write the output ZIP into.

    Returns:
        Absolute path to the created ZIP file.
    """
    # ── Pull index from DB ───────────────────────────────────────────────────
    conn = _connect(db_path)
    summaries = get_all_summaries(conn)
    conn.close()

    # ── Build index.json ─────────────────────────────────────────────────────
    index = summaries  # already [{id, title, summary, tags, category}]

    # ── Build metadata.json ──────────────────────────────────────────────────
    metadata = {
        "project_name": project_name,
        "source_url": source_url,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "total_chunks": len(summaries),
        "session_key": session_key,
        "status": "active",
    }

    # ── Write to temp dir, then zip ──────────────────────────────────────────
    tmp_dir = Path(tempfile.mkdtemp())
    try:
        index_path = tmp_dir / "index.json"
        metadata_path = tmp_dir / "metadata.json"

        index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        zip_path = Path(output_dir) / f"{session_key}.zip"

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(db_path, arcname="memory.db")
            zf.write(str(index_path), arcname="index.json")
            zf.write(str(metadata_path), arcname="metadata.json")

        return str(zip_path)

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── CLI entry point for manual testing ──────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 5:
        print(
            "Usage: python packager.py <db_path> <project_name> <source_url> <session_key> [output_dir]"
        )
        sys.exit(1)

    db_path = sys.argv[1]
    project_name = sys.argv[2]
    source_url = sys.argv[3]
    session_key = sys.argv[4]
    output_dir = sys.argv[5] if len(sys.argv) > 5 else "/tmp"

    out = create_package(db_path, project_name, source_url, session_key, output_dir)
    print(f"Package created: {out}")
