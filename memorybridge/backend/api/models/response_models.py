"""
models/response_models.py — MemoryBridge Phase 2
Pydantic v2 response schemas.
"""

from __future__ import annotations
from pydantic import BaseModel
from typing import Optional


class ChunkResult(BaseModel):
    id: str
    title: str
    summary: str
    detail: str
    code: Optional[str]
    tags: list[str]
    category: str
    similarity_score: float


class TopicItem(BaseModel):
    id: str
    title: str
    category: str
    retrieved: bool
    fetch_url: Optional[str] = None  # ready-to-use URL — call this to get chunk content


class IndexResponse(BaseModel):
    project: str
    source_url: str
    total_chunks: int
    retrieved: int
    remaining: int
    topics: list[TopicItem]


class QueryResponse(BaseModel):
    chunks: list[ChunkResult]
    total_returned: int
    remaining_chunks: int
    auto_archived: bool = False
    message: Optional[str] = None


class StatusResponse(BaseModel):
    project: str
    total_chunks: int
    retrieved: int
    remaining: int
    percent_complete: int
    status: str


class ArchiveResponse(BaseModel):
    status: str
    project: str
    archived_at: str


class PromptResponse(BaseModel):
    project: str
    session_key: str
    prompt: str


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    uptime_seconds: float
