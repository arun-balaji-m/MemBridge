"""
models/request_models.py — MemoryBridge Phase 2
Pydantic v2 request/query parameter schemas.
"""

from pydantic import BaseModel, Field


class QueryParams(BaseModel):
    key: str = Field(..., description="8-character session key")
    question: str = Field(..., min_length=1, description="Natural language question")
    top_k: int = Field(3, ge=1, le=10, description="Number of chunks to return")


class IndexParams(BaseModel):
    key: str = Field(..., description="8-character session key")


class StatusParams(BaseModel):
    key: str = Field(..., description="8-character session key")


class ArchiveParams(BaseModel):
    key: str = Field(..., description="8-character session key")


class PromptParams(BaseModel):
    key: str = Field(..., description="8-character session key")
