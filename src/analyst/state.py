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


def _append(left: list | None, right: list | None) -> list:
    """Reducer: accumulate per-cycle trace entries across the correction loop."""
    return (left or []) + (right or [])


class GraphState(TypedDict, total=False):
    """State threaded through the graph, including the self-correction cycle."""

    question: str
    intent: str
    sql: str
    columns: list[str]
    rows: list[tuple]
    answer: str
    error: str | None
    cycle_count: int      # incremented by diagnose; guards the 3-cycle cap
    diagnosis: str        # LLM explanation of what went wrong; injected into next generate_sql
    trace: Annotated[list[dict], _append]   # per-cycle: {cycle, sql_attempted, db_error, diagnosis}
    latency_ms: Annotated[dict[str, float], _merge]
    tokens: Annotated[dict[str, dict[str, int]], _merge]


@dataclass(frozen=True)
class Deps:
    """Injected into every node (closures in graph.py): config + LLM client."""

    cfg: Config
    llm: LLM
