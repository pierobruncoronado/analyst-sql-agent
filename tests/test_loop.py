"""Deterministic unit tests for the LangGraph self-correction loop mechanics.

These tests do NOT call any real API or DB — they mock both LLM and DB to verify:
  1. Routing functions behave correctly for all states.
  2. The full graph exhausts exactly 3 correction cycles when DB always fails.
  3. After exhaustion, synthesize receives the correct state and produces an honest decline.

No flakiness: LLM output is mocked, DB is mocked, results are deterministic.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from analyst.config import Config
from analyst.graph import _MAX_CYCLES, _route_classify, _route_execute, build_graph
from analyst.state import Deps


class _FakeLLM:
    """Minimal LLM double: classify → answerable, generate_sql → SELECT 1, text → fixed."""

    def tool_call(self, *, system: str, user: str, tool: dict) -> tuple[dict, dict]:
        tokens = {"input_tokens": 1, "output_tokens": 1}
        if tool["name"] == "classify_intent":
            return {"intent": "answerable"}, tokens
        return {"sql": "SELECT 1"}, tokens  # emit_sql

    def text(self, *, system: str, user: str) -> tuple[str, dict]:
        return "mock LLM response", {"input_tokens": 1, "output_tokens": 1}


@pytest.fixture
def deps() -> Deps:
    cfg = Config(database_url_ro="postgresql://fake/db", anthropic_api_key="sk-fake")
    return Deps(cfg=cfg, llm=_FakeLLM())


# ---------------------------------------------------------------------------
# Routing function unit tests — pure, no graph invocation
# ---------------------------------------------------------------------------

class TestRouteExecute:
    def test_success_routes_to_synthesize(self):
        assert _route_execute({"error": None, "cycle_count": 0}) == "synthesize"

    def test_error_below_cap_routes_to_diagnose(self):
        assert _route_execute({"error": "boom", "cycle_count": 0}) == "diagnose"
        assert _route_execute({"error": "boom", "cycle_count": _MAX_CYCLES - 1}) == "diagnose"

    def test_error_at_cap_routes_to_synthesize(self):
        assert _route_execute({"error": "boom", "cycle_count": _MAX_CYCLES}) == "synthesize"

    def test_error_above_cap_routes_to_synthesize(self):
        assert _route_execute({"error": "boom", "cycle_count": _MAX_CYCLES + 1}) == "synthesize"


class TestRouteClassify:
    def test_answerable_routes_to_generate_sql(self):
        assert _route_classify({"intent": "answerable"}) == "generate_sql"

    def test_out_of_schema_routes_to_reject(self):
        assert _route_classify({"intent": "out_of_schema"}) == "reject"

    def test_destructive_routes_to_reject(self):
        assert _route_classify({"intent": "destructive"}) == "reject"


# ---------------------------------------------------------------------------
# Full-graph integration with mocked DB — tests the cycle mechanic end-to-end
# ---------------------------------------------------------------------------

class TestLoopMechanic:
    def _invoke(self, deps: Deps, *, db_side_effect) -> dict:
        graph = build_graph(deps)
        with patch("analyst.nodes.run_readonly", side_effect=db_side_effect):
            return graph.invoke({
                "question": "How many foo?",
                "cycle_count": 0,
                "diagnosis": "",
                "latency_ms": {},
                "tokens": {},
            })

    def test_three_cycles_exhausted_on_persistent_db_error(self, deps):
        """DB always fails → graph runs exactly MAX_CYCLES correction cycles."""
        final = self._invoke(
            deps, db_side_effect=Exception("relation 'foo' does not exist")
        )
        assert final["cycle_count"] == _MAX_CYCLES, (
            f"Expected {_MAX_CYCLES} cycles, got {final['cycle_count']}"
        )
        assert final["error"] is not None

    def test_honest_decline_message_after_exhaustion(self, deps):
        """Synthesize produces an honest decline referencing the cycle count."""
        final = self._invoke(
            deps, db_side_effect=Exception("column 'x' does not exist")
        )
        answer = final.get("answer", "")
        assert "correction" in answer.lower(), (
            f"Expected 'correction' in decline message, got: {answer!r}"
        )

    def test_recovery_on_second_attempt(self, deps):
        """DB fails once then succeeds → cycle_count==1 and rows are returned."""
        call_count = 0

        def db_fail_once(cfg, sql):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("first attempt fails")
            return ["col"], [("result_row",)]

        final = self._invoke(deps, db_side_effect=db_fail_once)
        assert final["cycle_count"] == 1
        assert final["error"] is None
        assert final["rows"] == [("result_row",)]

    def test_cycle_count_increments_per_diagnose(self, deps):
        """cycle_count advances by 1 per diagnose node, not per execute_sql."""
        # Two failures → 2 diagnose calls → cycle_count == 2, then success
        call_count = 0

        def db_fail_twice(cfg, sql):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise Exception(f"failure {call_count}")
            return ["col"], [("ok",)]

        final = self._invoke(deps, db_side_effect=db_fail_twice)
        assert final["cycle_count"] == 2
        assert final["error"] is None
