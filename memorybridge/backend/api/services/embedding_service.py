"""
services/embedding_service.py — MemoryBridge Phase 2
Singleton wrapper around sentence-transformers.
The model is loaded once in the FastAPI lifespan and stored in app_state.
"""

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

log = logging.getLogger(__name__)

MAX_CHARS  = 800   # ~256 tokens — model hard limit; truncate detail before encoding
_semaphore: asyncio.Semaphore | None = None


def get_semaphore() -> asyncio.Semaphore:
    """Lazily create a semaphore that caps concurrent encode() calls to 4."""
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(4)
    return _semaphore


def _build_text(text: str) -> str:
    return text[:MAX_CHARS].strip()


def embed_sync(model: "SentenceTransformer", text: str) -> list[float]:
    """Blocking encode — must be called via run_in_executor."""
    vec = model.encode(_build_text(text), show_progress_bar=False)
    return vec.tolist()


async def embed_text(app_state: dict, text: str) -> list[float]:
    """
    Async entry point. Acquires semaphore, runs blocking encode in
    the default thread pool, returns 384-float list.
    """
    model = app_state.get("model")
    if model is None:
        raise RuntimeError("Embedding model not loaded. Is the server still starting?")

    sem = get_semaphore()
    async with sem:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, embed_sync, model, text)
