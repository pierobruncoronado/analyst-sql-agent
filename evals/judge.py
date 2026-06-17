"""LLM-as-judge: Haiku scores answer quality as 0 or 1.

Kept deliberately minimal: one call, one score, one line of reasoning.
A judge failure (API error, non-parseable response) is a harness error —
it is surfaced as score=-1 so the report distinguishes it from a real 0.
"""

from __future__ import annotations

import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent / "src"))

from analyst.llm import LLM

_SYSTEM = (
    "You are an evaluator for an AI business-analytics assistant. "
    "Score whether the actual answer correctly addresses the question "
    "according to the reference description. "
    "Reply with ONLY the digit '1' (correct) or '0' (wrong, incomplete, or hallucinated). "
    "No other text."
)


def judge(llm: LLM, question: str, reference: str, actual: str) -> tuple[int, str, dict]:
    """Return (score, raw_response, token_usage). score=-1 on harness error."""
    user = (
        f"Question: {question}\n\n"
        f"Reference (what a correct answer must convey): {reference}\n\n"
        f"Actual answer: {actual}\n\n"
        "Score (1 or 0):"
    )
    try:
        raw, tokens = llm.text(system=_SYSTEM, user=user)
        raw = raw.strip()
        score = 1 if raw.startswith("1") else 0
        return score, raw, tokens
    except Exception as exc:  # noqa: BLE001
        return -1, f"HARNESS ERROR: {exc}", {"input_tokens": 0, "output_tokens": 0}
