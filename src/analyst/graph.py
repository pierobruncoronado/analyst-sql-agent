"""LangGraph wiring — linear happy path for this session.

classify -> generate_sql -> execute_sql -> synthesize -> END.
The conditional edge on `intent` and the error -> diagnose -> regenerate cycle
(max 3) are the next session's work. The graph is built minimal-and-running
first; the cycle is what the project exists to demonstrate.
"""

from __future__ import annotations

from functools import partial

from langgraph.graph import END, START, StateGraph

from . import nodes
from .state import Deps, GraphState


def build_graph(deps: Deps):
    """Compile the linear state machine, with `deps` bound into each node."""
    g = StateGraph(GraphState)
    g.add_node("classify", partial(nodes.classify, deps=deps))
    g.add_node("generate_sql", partial(nodes.generate_sql, deps=deps))
    g.add_node("execute_sql", partial(nodes.execute_sql, deps=deps))
    g.add_node("synthesize", partial(nodes.synthesize, deps=deps))

    g.add_edge(START, "classify")
    g.add_edge("classify", "generate_sql")
    g.add_edge("generate_sql", "execute_sql")
    g.add_edge("execute_sql", "synthesize")
    g.add_edge("synthesize", END)
    return g.compile()
