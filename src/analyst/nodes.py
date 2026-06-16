"""Graph nodes — one responsibility each.

Happy path this session: classify (log-only) -> generate_sql -> execute_sql ->
synthesize. Each node times itself and records token usage; every LLM/DB call is
wrapped so a failure becomes an honest `error` in state rather than a crash.
"""

from __future__ import annotations

import time
from typing import Any

from .db import run_readonly
from .logging_utils import log_event
from .schema import SCHEMA_DESCRIPTION
from .state import Deps, GraphState

# --- Forced-tool schemas (valid JSON out, no free-text parsing) ---

_CLASSIFY_TOOL: dict[str, Any] = {
    "name": "classify_intent",
    "description": "Classify a question for a read-only sales-analytics SQL agent.",
    "input_schema": {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "enum": ["answerable", "out_of_schema", "destructive"],
                "description": (
                    "answerable: a read question about customers/products/orders/"
                    "order_items. out_of_schema: needs data not in the schema. "
                    "destructive: asks to modify/delete data or inject SQL."
                ),
            }
        },
        "required": ["intent"],
        "additionalProperties": False,
    },
}

_SQL_TOOL: dict[str, Any] = {
    "name": "emit_sql",
    "description": "Return a single read-only Postgres SELECT answering the question.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": "One SELECT statement. No DDL/DML, no semicolon chains.",
            }
        },
        "required": ["sql"],
        "additionalProperties": False,
    },
}


def _timed(fn):
    """Run fn(), return (result, elapsed_ms)."""
    start = time.perf_counter()
    result = fn()
    return result, round((time.perf_counter() - start) * 1000, 1)


def classify(state: GraphState, deps: Deps) -> dict[str, Any]:
    """Forced-tool classification. Log-only this session: graph proceeds regardless."""
    question = state["question"]
    system = "You classify questions for a read-only sales database.\n\n" + SCHEMA_DESCRIPTION
    (out, tokens), ms = _timed(
        lambda: deps.llm.tool_call(system=system, user=question, tool=_CLASSIFY_TOOL)
    )
    intent = out["intent"]
    log_event("classify", intent=intent, latency_ms=ms, tokens=tokens)
    return {"intent": intent, "latency_ms": {"classify": ms}, "tokens": {"classify": tokens}}


def generate_sql(state: GraphState, deps: Deps) -> dict[str, Any]:
    """Generate one read-only SELECT via forced tool-use."""
    question = state["question"]
    system = (
        "You write a single read-only Postgres SELECT for the user's question.\n"
        "Use ONLY the tables/columns below. Never write to the database.\n\n"
        + SCHEMA_DESCRIPTION
    )
    (out, tokens), ms = _timed(
        lambda: deps.llm.tool_call(system=system, user=question, tool=_SQL_TOOL)
    )
    sql = out["sql"].strip()
    log_event("generate_sql", sql=sql, latency_ms=ms, tokens=tokens)
    return {"sql": sql, "latency_ms": {"generate_sql": ms}, "tokens": {"generate_sql": tokens}}


def execute_sql(state: GraphState, deps: Deps) -> dict[str, Any]:
    """Run the SQL read-only. DB errors are recorded (the self-correct loop is v-next)."""
    sql = state["sql"]
    try:
        (columns, rows), ms = _timed(lambda: run_readonly(deps.cfg, sql))
    except Exception as exc:  # noqa: BLE001 — surface honestly, don't crash
        log_event("execute_sql", status="error", error=str(exc))
        return {"error": str(exc), "columns": [], "rows": [], "latency_ms": {"execute_sql": 0.0}}
    log_event("execute_sql", status="ok", row_count=len(rows), latency_ms=ms)
    return {
        "columns": columns,
        "rows": rows,
        "error": None,
        "latency_ms": {"execute_sql": ms},
    }


def synthesize(state: GraphState, deps: Deps) -> dict[str, Any]:
    """Write the answer sentence in the question's language, grounded on the rows."""
    if state.get("error"):
        msg = "I couldn't run a safe query for that question, so I can't answer it confidently."
        log_event("synthesize", status="declined")
        return {"answer": msg, "latency_ms": {"synthesize": 0.0}}

    question = state["question"]
    columns = state.get("columns", [])
    rows = state.get("rows", [])
    system = (
        "You report a SQL result to the user. Answer in the SAME language as the question, "
        "in one or two sentences. Use ONLY the numbers in the result rows — never invent data. "
        "If the result is empty, say so plainly."
    )
    user = (
        f"Question: {question}\n"
        f"Columns: {columns}\n"
        f"Rows (capped): {rows}\n"
    )
    (answer, tokens), ms = _timed(lambda: deps.llm.text(system=system, user=user))
    log_event("synthesize", status="ok", latency_ms=ms, tokens=tokens)
    return {
        "answer": answer.strip(),
        "latency_ms": {"synthesize": ms},
        "tokens": {"synthesize": tokens},
    }
