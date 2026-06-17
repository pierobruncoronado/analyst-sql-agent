"""Eval harness — run all golden cases, report baseline, exit 0/1 for CI.

Usage:
    uv run python evals/run.py

Exit 0 if all hard assertions pass. Exit 1 if any fail.
Soft assertions (cycles_soft_min) print a warning but do not affect the exit code.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from datetime import datetime

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent / "src"))

from analyst.config import load_config
from analyst.graph import build_graph
from analyst.llm import LLM
from analyst.state import Deps

from cases import CASES, EvalCase
from judge import judge as llm_judge

PASS = "ok"
FAIL = "FAIL"
WARN = "warn"


@dataclass
class AssertionResult:
    name: str
    passed: bool        # False means hard failure; None-like means soft
    is_soft: bool
    detail: str


@dataclass
class CaseResult:
    case: EvalCase
    intent: str | None
    sql: str | None
    cycles: int
    answer: str
    latency_ms: dict
    tokens: dict
    assertions: list[AssertionResult]
    judge_score: int | None     # None = not judged; -1 = harness error
    judge_tokens: dict

    @property
    def total_input_tokens(self) -> int:
        base = sum(v.get("input_tokens", 0) for v in self.tokens.values())
        return base + self.judge_tokens.get("input_tokens", 0)

    @property
    def total_output_tokens(self) -> int:
        base = sum(v.get("output_tokens", 0) for v in self.tokens.values())
        return base + self.judge_tokens.get("output_tokens", 0)

    @property
    def total_latency_ms(self) -> float:
        return sum(self.latency_ms.values())

    @property
    def hard_passed(self) -> bool:
        return all(a.passed for a in self.assertions if not a.is_soft)

    @property
    def soft_warnings(self) -> list[AssertionResult]:
        return [a for a in self.assertions if a.is_soft and not a.passed]


def run_case(case: EvalCase, graph, llm: LLM) -> CaseResult:
    t0 = time.perf_counter()
    final = graph.invoke({
        "question": case.question,
        "cycle_count": 0,
        "diagnosis": "",
        "latency_ms": {},
        "tokens": {},
    })
    _ = time.perf_counter() - t0  # wall time (graph already tracks stage latency)

    intent = final.get("intent")
    sql = final.get("sql")
    cycles = final.get("cycle_count", 0)
    answer = final.get("answer", "")
    latency = final.get("latency_ms", {})
    tokens = final.get("tokens", {})

    assertions: list[AssertionResult] = []

    # Hard: intent matches
    assertions.append(AssertionResult(
        name="intent",
        passed=(intent == case.expected_intent),
        is_soft=False,
        detail=f"{intent!r} (expected {case.expected_intent!r})",
    ))

    # Hard: sql null when expected
    if case.sql_must_be_null:
        assertions.append(AssertionResult(
            name="sql_null",
            passed=(sql is None),
            is_soft=False,
            detail="sql is None" if sql is None else f"sql present: {sql[:60]}…",
        ))

    # Hard: answer substrings
    for substr in case.answer_must_contain:
        assertions.append(AssertionResult(
            name=f"answer_contains[{substr!r}]",
            passed=(substr in answer),
            is_soft=False,
            detail="found" if substr in answer else f"NOT found in: {answer[:120]}",
        ))

    # Hard: SQL substrings (only when sql is not None)
    if sql is not None:
        for substr in case.sql_must_contain:
            assertions.append(AssertionResult(
                name=f"sql_contains[{substr!r}]",
                passed=(substr.upper() in sql.upper()),
                is_soft=False,
                detail="found" if substr.upper() in sql.upper() else "NOT in SQL",
            ))

    # Hard: LLM-as-judge
    judge_score: int | None = None
    judge_tokens: dict = {}
    if case.judge_reference is not None:
        judge_score, judge_raw, judge_tokens = llm_judge(
            llm, case.question, case.judge_reference, answer
        )
        passed = (judge_score == 1)
        detail = f"score={judge_score} raw={judge_raw[:60]!r}"
        if judge_score == -1:
            detail = f"HARNESS ERROR — {judge_raw}"
        assertions.append(AssertionResult(
            name="judge",
            passed=passed,
            is_soft=False,
            detail=detail,
        ))

    # Soft: cycles minimum
    if case.cycles_soft_min > 0:
        assertions.append(AssertionResult(
            name=f"cycles_soft_min={case.cycles_soft_min}",
            passed=(cycles >= case.cycles_soft_min),
            is_soft=True,
            detail=f"cycles={cycles} (expected >= {case.cycles_soft_min})",
        ))

    return CaseResult(
        case=case,
        intent=intent,
        sql=sql,
        cycles=cycles,
        answer=answer,
        latency_ms=latency,
        tokens=tokens,
        assertions=assertions,
        judge_score=judge_score,
        judge_tokens=judge_tokens,
    )


def print_report(results: list[CaseResult]) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    sep = "=" * 64
    print(f"\n{sep}")
    print(f" ANALYST EVAL SUITE — {now}")
    print(sep)

    for i, r in enumerate(results, 1):
        icon = PASS if r.hard_passed else FAIL
        print(f"\n[{i}/{len(results)}] {r.case.id}  {icon}")
        print(f"  Q: {r.case.question}")
        for a in r.assertions:
            if a.is_soft:
                sym = PASS if a.passed else WARN
                tag = "(soft)"
            else:
                sym = PASS if a.passed else FAIL
                tag = ""
            print(f"  {sym} {a.name:<36} {a.detail}  {tag}")
        print(f"  cycles  : {r.cycles}"
              + ("  [soft warning]" if r.soft_warnings else ""))
        lat_str = "  ".join(f"{k}:{v:.0f}ms" for k, v in r.latency_ms.items())
        print(f"  latency : {r.total_latency_ms:.0f}ms total  ({lat_str})")
        cost = r.total_input_tokens * 1e-6 + r.total_output_tokens * 5e-6
        print(f"  tokens  : {r.total_input_tokens}in {r.total_output_tokens}out"
              f"  → ${cost:.4f}")

    # Summary
    hard_pass = sum(1 for r in results if r.hard_passed)
    judge_cases = [r for r in results if r.judge_score is not None]
    judge_pass = sum(1 for r in results if r.judge_score == 1)
    soft_warns = sum(len(r.soft_warnings) for r in results)
    total_in = sum(r.total_input_tokens for r in results)
    total_out = sum(r.total_output_tokens for r in results)
    total_cost = total_in * 1e-6 + total_out * 5e-6
    total_lat = sum(r.total_latency_ms for r in results)

    print(f"\n{sep}")
    print(" SUMMARY")
    print(sep)
    print(f"  Cases   : {hard_pass}/{len(results)} hard assertions passed")
    if judge_cases:
        print(f"  Judge   : {judge_pass}/{len(judge_cases)} scored 1")
    if soft_warns:
        print(f"  Soft    : {soft_warns} warning(s) (do not affect exit code)")
    print(f"  Cost    : {total_in}in / {total_out}out → ${total_cost:.4f} total")
    print(f"  Time    : {total_lat / 1000:.1f}s total")

    ok = hard_pass == len(results)
    verdict = "PASS" if ok else "FAIL"
    print(f"  Result  : {verdict} (exit {'0' if ok else '1'})")
    print(sep + "\n")


def main() -> int:
    try:
        cfg = load_config()
    except RuntimeError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    llm = LLM(cfg)
    deps = Deps(cfg=cfg, llm=llm)
    graph = build_graph(deps)

    print(f"Running {len(CASES)} eval cases…", flush=True)
    results: list[CaseResult] = []
    for case in CASES:
        print(f"  > {case.id}", end="", flush=True)
        r = run_case(case, graph, llm)
        icon = PASS if r.hard_passed else FAIL
        print(f"  {icon}  ({r.total_latency_ms:.0f}ms)", flush=True)
        results.append(r)

    print_report(results)
    return 0 if all(r.hard_passed for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
