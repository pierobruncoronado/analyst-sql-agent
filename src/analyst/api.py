"""FastAPI HTTP layer for the conversational SQL agent.

One endpoint: POST /ask  (+ GET / for health checks).
The graph is compiled once at startup and reused across requests.
Rate limit: 10 req/minute per IP (spec §4 anti-abuso). Limit exceeded → 429.
Validation: empty or >500-char question → 422 (malformed request, not agent response).
Rejections (out_of_schema, destructive) → 200 + intent field (agent responded correctly).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .config import load_config
from .graph import build_graph
from .llm import LLM
from .logging_utils import log_event
from .state import Deps

_RATE_LIMIT = "10/minute"

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    cfg = load_config()
    deps = Deps(cfg=cfg, llm=LLM(cfg))
    app.state.graph = build_graph(deps)
    log_event("startup", model=cfg.model, row_cap=cfg.row_cap)
    yield
    log_event("shutdown")


app = FastAPI(title="Analyst — conversational SQL agent", lifespan=_lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)


class AskResponse(BaseModel):
    answer: str
    intent: str | None = None
    sql: str | None = None
    cycles: int = 0
    latency_ms: dict = Field(default_factory=dict)
    tokens: dict = Field(default_factory=dict)


@app.get("/")
def health():
    """Health check — Railway polls this to decide if traffic can be routed."""
    return {"status": "ok", "model": "claude-haiku-4-5"}


@app.post("/ask", response_model=AskResponse)
@limiter.limit(_RATE_LIMIT)
def ask(request: Request, body: AskRequest) -> AskResponse:
    """Run the LangGraph agent end-to-end and return structured results.

    Sync def → FastAPI runs this in a threadpool so the event loop stays free.
    422 on bad input (FastAPI/Pydantic), 200 on all agent responses including
    rejections (intent=destructive/out_of_schema), 429 if rate limit exceeded.
    """
    final = app.state.graph.invoke({
        "question": body.question,
        "cycle_count": 0,
        "diagnosis": "",
        "latency_ms": {},
        "tokens": {},
    })
    latency = final.get("latency_ms", {})
    total_ms = round(sum(latency.values()), 1)
    log_event(
        "api_ask",
        intent=final.get("intent"),
        cycles=final.get("cycle_count", 0),
        total_latency_ms=total_ms,
    )
    return AskResponse(
        answer=final.get("answer", ""),
        intent=final.get("intent"),
        sql=final.get("sql"),
        cycles=final.get("cycle_count", 0),
        latency_ms=latency,
        tokens=final.get("tokens", {}),
    )
