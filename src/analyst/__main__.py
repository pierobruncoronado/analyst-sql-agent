"""CLI runner: `uv run python -m analyst "<question>"`.

Builds config + LLM + graph, runs one question end-to-end, prints the answer
plus the run summary (intent, SQL, rows, per-stage latency, tokens).
"""

from __future__ import annotations

import sys

from .config import load_config
from .graph import build_graph
from .llm import LLM
from .state import Deps


def main() -> int:
    question = " ".join(sys.argv[1:]).strip()
    if not question:  # fail-closed: empty input is rejected, not assumed
        print('usage: uv run python -m analyst "<question>"', file=sys.stderr)
        return 2

    try:
        cfg = load_config()
    except RuntimeError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    deps = Deps(cfg=cfg, llm=LLM(cfg))
    graph = build_graph(deps)

    final = graph.invoke({
        "question": question,
        "cycle_count": 0,
        "diagnosis": "",
        "latency_ms": {},
        "tokens": {},
    })

    latency = final.get("latency_ms", {})
    tokens = final.get("tokens", {})
    total_in = sum(t.get("input_tokens", 0) for t in tokens.values())
    total_out = sum(t.get("output_tokens", 0) for t in tokens.values())

    print("\n--- ANSWER ---")
    print(final.get("answer", "(no answer)"))
    print("\n--- RUN SUMMARY ---")
    print(f"intent:        {final.get('intent')}")
    print(f"cycles:        {final.get('cycle_count', 0)}")
    print(f"sql:           {final.get('sql')}")
    print(f"rows:          {len(final.get('rows', []))}")
    print(f"latency:       {latency}  total={round(sum(latency.values()), 1)} ms")
    print(f"tokens:        in={total_in} out={total_out}  by_stage={tokens}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
