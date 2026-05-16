"""
routers/prompt.py — MemoryBridge Phase 2
GET /prompt?key=<session_key>
Returns a ready-to-paste LLM prompt that teaches the LLM to use
this API to restore project context.
"""

import os
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from api.services.session_service import resolve_session
from api.models.response_models import PromptResponse

router = APIRouter()

PROMPT_TEMPLATE = """\
I'm continuing work on "{project}".
My full project context is stored in a MemoryBridge memory system.

API Base: {api_base}
Session Key: {key}

Retrieve context before answering anything about this project:

STEP 1 — List topics (GET, works everywhere):
  {api_base}/index?key={key}

STEP 2 — Fetch relevant chunks. Use whichever method your environment supports:

  Option A — GET (Claude, ChatGPT browsing, any browser):
    {api_base}/query?key={key}&question=<url-encoded-question>&top_k=3
    Example: {api_base}/query?key={key}&question=how+does+authentication+work&top_k=3

  Option B — POST with JSON body (ChatGPT Custom GPT Actions, API clients):
    POST {api_base}/query
    Content-Type: application/json
    {{"key": "{key}", "question": "<your question>", "top_k": 3}}

STEP 3 — Answer using the retrieved chunks.
STEP 4 — Repeat Step 2 as new topics arise.

No authentication needed for any request.
Start now with Step 1 and summarize the project and where we left off.\
"""


@router.get("/prompt", response_model=PromptResponse)
async def get_prompt(
    key: str,
    authorization: Optional[str] = Header(None, description="Bearer <google_access_token>"),
):
    token = _extract_token(authorization)
    entry = await resolve_session(key, token)

    api_base = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
    project  = entry.metadata.get("project_name", key)

    prompt = PROMPT_TEMPLATE.format(
        project=project,
        api_base=api_base,
        key=key,
    )

    return PromptResponse(
        project=project,
        session_key=key,
        prompt=prompt,
    )


def _extract_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authorization header must be 'Bearer <token>'",
        )
    return authorization[len("Bearer "):]
