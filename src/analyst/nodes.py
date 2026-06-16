"""Graph nodes — one responsibility each.

classify -> (answerable) -> generate_sql -> execute_sql -> synthesize
         -> (out_of_schema | destructive) -> reject

execute_sql error path: -> diagnose -> generate_sql (cycle, max 3)
                           cap exhausted -> synthesize (honest decline)

Security decision: the reject node NEVER calls the LLM. A destructive or
out-of-schema question gets a fixed template response — deterministic, zero
risk of prompt-injection leaking into a model call. The defense lives at the
connection layer (analyst_ro role) + here in the reject path + the schema
validation the LLM prompt enforces. Defense in depth, not just a prompt.
"""

from __future__ import annotations

import time
from typing import Any

from .db import run_readonly
from .logging_utils import log_event
from .schema import SCHEMA_DESCRIPTION
from .state import Deps, GraphState

# --- Forced-tool schemas ---

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

# Fixed rejection messages — no LLM involved, ever.
_REJECT_MSG = {
    "destructive": (
        "I won't execute write operations, DROP/DELETE statements, or potentially "
        "harmful queries. / No ejecutaré operaciones de escritura, sentencias "
        "DROP/DELETE ni consultas potencialmente dañinas."
    ),
    "out_of_schema": (
        "I can only answer questions about the sales data I have access to: "
        "customers, products, orders, and order items. "
        "That question requires data that isn't in my schema. / "
        "Solo puedo responder preguntas sobre: clientes, productos, pedidos e ítems "
        "de pedidos. Esa pregunta requiere datos que no están en mi esquema."
    ),
}


def _timed(fn):
    """Run fn(), return (result, elapsed_ms)."""
    start = time.perf_counter()
    result = fn()
    return result, round((time.perf_counter() - start) * 1000, 1)


# --- Nodes ---

def classify(state: GraphState, deps: Deps) -> dict[str, Any]:
    """Forced-tool classification. Result drives the conditional edge in graph.py."""
    question = state["question"]
    system = "You classify questions for a read-only sales database.\n\n" + SCHEMA_DESCRIPTION
    (out, tokens), ms = _timed(
        lambda: deps.llm.tool_call(system=system, user=question, tool=_CLASSIFY_TOOL)
    )
    intent = out["intent"]
    log_event("classify", intent=intent, latency_ms=ms, tokens=tokens)
    return {"intent": intent, "latency_ms": {"classify": ms}, "tokens": {"classify": tokens}}


def reject(state: GraphState, deps: Deps) -> dict[str, Any]:  # noqa: ARG001
    """Fixed-template rejection — no LLM call, no SQL execution. Security path."""
    intent = state.get("intent", "destructive")
    msg = _REJECT_MSG.get(intent, _REJECT_MSG["out_of_schema"])
    log_event("reject", intent=intent)
    return {"answer": msg, "latency_ms": {"reject": 0.0}}


def generate_sql(state: GraphState, deps: Deps) -> dict[str, Any]:
    """Generate one read-only SELECT via forced tool-use.

    On retries, the prior failed SQL + LLM diagnosis are injected so Haiku
    can correct the specific mistake rather than repeating it.
    """
    question = state["question"]
    diagnosis = state.get("diagnosis", "")
    prior_sql = state.get("sql", "")
    cycle = state.get("cycle_count", 0)

    system = (
        "You write a single read-only Postgres SELECT for the user's question.\n"
        "Use ONLY the tables/columns below. Never write to the database.\n\n"
        + SCHEMA_DESCRIPTION
    )
    if diagnosis and prior_sql:
        user = (
            f"Question: {question}\n\n"
            f"--- Previous attempt (cycle {cycle}) failed ---\n"
            f"SQL tried:\n{prior_sql}\n\n"
            f"Diagnosis:\n{diagnosis}\n\n"
            "Please write a corrected SELECT that avoids the problem above."
        )
    else:
        user = question

    (out, tokens), ms = _timed(
        lambda: deps.llm.tool_call(system=system, user=user, tool=_SQL_TOOL)
    )
    sql = out["sql"].strip()
    log_event("generate_sql", sql=sql, cycle=cycle, latency_ms=ms, tokens=tokens)
    return {"sql": sql, "latency_ms": {f"generate_sql_{cycle}": ms}, "tokens": {f"generate_sql_{cycle}": tokens}}


def execute_sql(state: GraphState, deps: Deps) -> dict[str, Any]:
    """Run the SQL read-only. Errors are recorded for the self-correction cycle."""
    sql = state["sql"]
    cycle = state.get("cycle_count", 0)
    try:
        (columns, rows), ms = _timed(lambda: run_readonly(deps.cfg, sql))
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
        log_event("execute_sql", status="error", cycle=cycle, error=err)
        return {
            "error": err,
            "columns": [],
            "rows": [],
            "latency_ms": {f"execute_sql_{cycle}": 0.0},
        }
    log_event("execute_sql", status="ok", cycle=cycle, row_count=len(rows), latency_ms=ms)
    return {
        "columns": columns,
        "rows": rows,
        "error": None,
        "latency_ms": {f"execute_sql_{cycle}": ms},
    }


def diagnose(state: GraphState, deps: Deps) -> dict[str, Any]:
    """LLM reads the DB error + failed SQL, writes a diagnosis, increments cycle_count.

    Logs both the raw DB error (for observability/error-class tracking) and the
    LLM-written diagnosis (for the next generate_sql prompt).
    """
    question = state["question"]
    failed_sql = state.get("sql", "")
    raw_error = state.get("error", "")
    cycle = state.get("cycle_count", 0)

    system = (
        "You are a SQL debugging assistant for a Postgres read-only sales database.\n"
        "Given a failed SQL query and its database error, write a concise diagnosis "
        "(2-3 sentences): what went wrong and what the corrected query should do differently.\n\n"
        + SCHEMA_DESCRIPTION
    )
    user = (
        f"Question the user asked: {question}\n\n"
        f"SQL that failed:\n{failed_sql}\n\n"
        f"Database error:\n{raw_error}"
    )
    (diagnosis_text, tokens), ms = _timed(lambda: deps.llm.text(system=system, user=user))
    new_cycle = cycle + 1
    log_event(
        "diagnose",
        cycle=new_cycle,
        raw_db_error=raw_error,
        diagnosis=diagnosis_text.strip(),
        latency_ms=ms,
        tokens=tokens,
    )
    return {
        "diagnosis": diagnosis_text.strip(),
        "cycle_count": new_cycle,
        "latency_ms": {f"diagnose_{new_cycle}": ms},
        "tokens": {f"diagnose_{new_cycle}": tokens},
    }


def synthesize(state: GraphState, deps: Deps) -> dict[str, Any]:
    """Write the answer sentence in the question's language, grounded on the rows."""
    error = state.get("error")
    cycle_count = state.get("cycle_count", 0)

    if error:
        diagnosis = state.get("diagnosis", "")
        if cycle_count >= 3:
            msg = (
                f"After the initial attempt plus {cycle_count} correction cycle(s), "
                "I couldn't generate a valid SQL query for that question. "
                f"Last known issue: {diagnosis}"
            )
        else:
            msg = "I couldn't run a safe query for that question, so I can't answer it confidently."
        log_event("synthesize", status="declined", cycle_count=cycle_count)
        return {"answer": msg, "latency_ms": {"synthesize": 0.0}}

    question = state["question"]
    columns = state.get("columns", [])
    rows = state.get("rows", [])
    cycle_count_label = f" (resolved after {cycle_count} correction cycle(s))" if cycle_count > 0 else ""
    system = (
        "You report a SQL result to the user. Answer in the SAME language as the question, "
        "in one or two sentences. Use ONLY the numbers in the result rows — never invent data. "
        "If the result is empty, say so plainly."
    )
    user = (
        f"Question: {question}{cycle_count_label}\n"
        f"Columns: {columns}\n"
        f"Rows (capped): {rows}\n"
    )
    (answer, tokens), ms = _timed(lambda: deps.llm.text(system=system, user=user))
    log_event("synthesize", status="ok", cycle_count=cycle_count, latency_ms=ms, tokens=tokens)
    return {
        "answer": answer.strip(),
        "latency_ms": {"synthesize": ms},
        "tokens": {"synthesize": tokens},
    }
