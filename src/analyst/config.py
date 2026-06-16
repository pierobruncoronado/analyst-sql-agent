"""Runtime configuration: env, model id, execution guardrails.

Secrets come from `.env` only (never committed). Validation is fail-closed:
a missing DB URL or API key raises here, before any node runs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv(override=False)  # Railway env vars take precedence over any local .env

# Haiku by default (spec: classification + SQL generation). Bump to Sonnet only if
# evals demand it — decided by data, not intuition. Verified against the claude-api
# reference: bare id, no date suffix.
DEFAULT_MODEL = "claude-haiku-4-5"


@dataclass(frozen=True)
class Config:
    """Immutable runtime config. Built once in __main__, threaded through nodes."""

    database_url_ro: str
    anthropic_api_key: str
    model: str = DEFAULT_MODEL
    row_cap: int = 100          # fetchmany cap — runaway-result protection
    statement_timeout_ms: int = 5000  # per-query DB timeout
    max_tokens: int = 1024      # generous for SQL + a one-sentence answer


def load_config() -> Config:
    """Read + validate env. Fail-closed: missing required secret → raise."""
    ro = os.environ.get("DATABASE_URL_RO", "").strip()
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not ro:
        raise RuntimeError("DATABASE_URL_RO is not set (read-only DB URL). Check .env.")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Paste it into .env.")
    return Config(database_url_ro=ro, anthropic_api_key=key)
