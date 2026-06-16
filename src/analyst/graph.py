"""LangGraph wiring — state machine with a self-correction cycle.

classify ──► (answerable) ──► generate_sql ──► execute_sql ──► synthesize
         └─► (out_of_schema | destructive) ──► reject ──► END

execute_sql error path (cycle_count < 3): ──► diagnose ──► generate_sql  (cycle)
execute_sql error path (cycle_count >= 3): ──► synthesize  (exhausted, honest decline)
"""

from __future__ import annotations

from functools import partial

from langgraph.graph import END, START, StateGraph

from . import nodes
from .state import Deps, GraphState

_MAX_CYCLES = 3


def _route_classify(state: GraphState) -> str:
    """After classify: answerable -> generate_sql; everything else -> reject."""
    return "generate_sql" if state.get("intent") == "answerable" else "reject"


def _route_execute(state: GraphState) -> str:
    """After execute_sql: success -> synthesize; error -> diagnose or synthesize (cap)."""
    if not state.get("error"):
        return "synthesize"
    if state.get("cycle_count", 0) < _MAX_CYCLES:
        return "diagnose"
    return "synthesize"


def build_graph(deps: Deps):
    """Compile the state machine with reject branch and self-correction cycle."""
    g = StateGraph(GraphState)

    g.add_node("classify",     partial(nodes.classify,     deps=deps))
    g.add_node("reject",       partial(nodes.reject,       deps=deps))
    g.add_node("generate_sql", partial(nodes.generate_sql, deps=deps))
    g.add_node("execute_sql",  partial(nodes.execute_sql,  deps=deps))
    g.add_node("diagnose",     partial(nodes.diagnose,     deps=deps))
    g.add_node("synthesize",   partial(nodes.synthesize,   deps=deps))

    g.add_edge(START, "classify")
    g.add_conditional_edges("classify", _route_classify, ["generate_sql", "reject"])
    g.add_edge("reject", END)
    g.add_edge("generate_sql", "execute_sql")
    g.add_conditional_edges("execute_sql", _route_execute, ["synthesize", "diagnose"])
    g.add_edge("diagnose", "generate_sql")   # ← the cycle
    g.add_edge("synthesize", END)

    return g.compile()
