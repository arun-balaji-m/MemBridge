"""
main.py — MemoryBridge Phase 2
FastAPI application entry point.

Lifespan:
  - Starts cache TTL eviction background task
  - Cleans up on shutdown

Endpoints wired:
  GET  /health
  GET  /index
  GET  /query
  GET  /status
  POST /archive
  GET  /prompt
"""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)

log = logging.getLogger(__name__)

from api.state import app_state  # noqa: E402
from api.utils.cache import eviction_loop  # noqa: E402

# ── Routers ───────────────────────────────────────────────────────────────────
from api.routers import index, query, status, archive, prompt  # noqa: E402


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    log.info("MemoryBridge API starting…")

    app_state["start_time"] = time.monotonic()

    # Start cache eviction background task
    ttl = float(os.getenv("CACHE_TTL_SECONDS", "3600"))

    eviction_task = asyncio.create_task(eviction_loop(ttl=ttl))
    app_state["eviction_task"] = eviction_task

    log.info("Cache eviction task started (TTL=%.0fs).", ttl)
    log.info("MemoryBridge API ready.")

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    log.info("Shutting down…")

    eviction_task.cancel()

    try:
        await eviction_task
    except asyncio.CancelledError:
        pass

    app_state.clear()

    log.info("Shutdown complete.")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="MemoryBridge API",
    description="Retrieval API for MemoryBridge memory packages stored in Google Drive.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(index.router, tags=["Memory"])
app.include_router(query.router, tags=["Memory"])
app.include_router(status.router, tags=["Memory"])
app.include_router(archive.router, tags=["Memory"])
app.include_router(prompt.router, tags=["LLM"])


# ── Health Check ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health():
    uptime = time.monotonic() - app_state.get(
        "start_time",
        time.monotonic()
    )

    return {
        "status": "ok",
        "embedder_proxy": "active",
        "uptime_seconds": round(uptime, 1),
    }


# ── Embed Proxy ───────────────────────────────────────────────────────────────

@app.post("/embed", tags=["System"])
async def proxy_embed(request: Request):
    """
    Proxy POST /embed to Phase 1 Flask embedder running on localhost:8765.
    """

    body = await request.json()

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            "http://localhost:8765/embed",
            json=body,
            timeout=120.0
        )

        resp.raise_for_status()

        return resp.json()


# ── Store Proxy ───────────────────────────────────────────────────────────────

@app.post("/store", tags=["System"])
async def proxy_store(request: Request):
    """
    Proxy POST /store to Phase 1 Flask embedder running on localhost:8765.
    """

    body = await request.json()

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            "http://localhost:8765/store",
            json=body,
            timeout=120.0
        )

        resp.raise_for_status()

        return resp.json()


# ── Dev Entry Point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))

    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )