"""
routers/prompt.py — MemoryBridge Phase 2
GET /prompt?key=<session_key>
Returns a ready-to-paste LLM prompt that teaches the LLM to use
this API to restore project context.
"""

import os
from fastapi import APIRouter, Header, HTTPException
from api.services.session_service import resolve_session
from api.models.response_models import PromptResponse

router = APIRouter()

PROMPT_TEMPLATE = """\
I'm continuing work on "{project}".
My full project context is stored externally in a memory system.

API Base: {api_base}
Session Key: {key}

Before answering anything about this project, you MUST:

1. Call GET {api_base}/index?key={key}
   → Read all available topics and decide which are relevant to the current question.

2. Call GET {api_base}/query?question=<your relevant question>&key={key}&top_k=3
   → This returns the most relevant context chunks. Use them as your working memory.

3. Answer using the retrieved chunks as context.

4. Repeat steps 2–3 as the conversation continues and new topics arise.

5. Call GET {api_base}/status?key={key} at any time to see retrieval progress.

Start now: call /index and summarize what project we are working on and where we left off.\
"""


@router.get("/prompt", response_model=PromptResponse)
async def get_prompt(
    key: str,
    authorization: str = Header(..., description="Bearer <google_access_token>"),
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


def _extract_token(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authorization header must be 'Bearer <token>'",
        )
    return authorization[len("Bearer "):]
