"""Typed graph state + shared node dependencies.

latency_ms and tokens use a merge reducer so each node contributes only its own
slice and LangGraph accumulates them across the run (instead of overwriting).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, TypedDict

from .config import Config
from .llm import LLM


def _merge(left: dict, right: dict) -> dict:
    """Reducer: shallow-merge per-stage instrumentation dicts."""
    return {**left, **right}


class GraphState(TypedDict, total=False):
    """State threaded through the linear graph (one cycle later, in v2)."""

    question: str
    intent: str
    sql: str
    columns: list[str]
    rows: list[tuple]
    answer: str
    error: str | None
    latency_ms: Annotated[dict[str, float], _merge]
    tokens: Annotated[dict[str, dict[str, int]], _merge]


@dataclass(frozen=True)
class Deps:
    """Injected into every node (closures in graph.py): config + LLM client."""

    cfg: Config
    llm: LLM
