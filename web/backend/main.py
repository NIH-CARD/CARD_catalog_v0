"""FastAPI backend for the CARD Catalog React app.

Stub serving a single ``POST /api/analyze`` endpoint that proxies Anthropic.
Only purpose is to keep the API key off the browser; everything else
(filtering, faceting, table rendering) happens client-side in React.

Run locally::

    cd web/backend
    pip install -r requirements.txt
    ANTHROPIC_API_KEY=... uvicorn main:app --reload --port 8000
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

app = FastAPI(title="CARD Catalog API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    page: str = Field(..., description="Page identifier: publications, resources, code, …")
    context: str = Field(..., description="Filtered-subset summary block to feed the model")
    model: str = Field("claude-sonnet-4-5", description="Claude model id")
    max_tokens: int = Field(2000, ge=100, le=8000)


class AnalyzeResponse(BaseModel):
    page: str
    model: str
    text: str


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    try:
        # Imported lazily so the server boots even without the SDK
        import anthropic
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=f"anthropic SDK missing: {exc}") from exc

    client = anthropic.Anthropic(api_key=api_key)
    try:
        msg = client.messages.create(
            model=req.model,
            max_tokens=req.max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"You are analysing the '{req.page}' subset of the CARD Catalog. "
                        "Provide a concise summary with key patterns, gaps, and recommendations.\n\n"
                        f"Context:\n{req.context}"
                    ),
                }
            ],
        )
    except Exception as exc:  # surface upstream errors to the client
        logger.exception("Anthropic call failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    text = "".join(
        block.text for block in msg.content if getattr(block, "type", "") == "text"
    )
    return AnalyzeResponse(page=req.page, model=req.model, text=text)
