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

Before answering anything about this project, you MUST retrieve context by calling these endpoints:

1. GET {api_base}/index?key={key}
   → Lists all available topics. Read them and decide which are relevant.

2. POST {api_base}/query
   Content-Type: application/json
   Body: {{"key": "{key}", "question": "<your relevant question>", "top_k": 3}}
   → Returns the most relevant context chunks. Use them as your working memory.

3. Answer using the retrieved chunks as context.

4. Repeat step 2 as new topics arise in the conversation.

5. GET {api_base}/status?key={key}
   → Check retrieval progress at any time.

No authentication headers are needed.

Start now: call GET {api_base}/index?key={key} and summarize what project we are working on and where we left off.\
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
