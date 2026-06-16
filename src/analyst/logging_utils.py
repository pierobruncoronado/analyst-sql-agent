"""Structured logging: one JSON line per event to stdout, no PII."""

from __future__ import annotations

import json
import sys
from typing import Any


def log_event(event: str, **fields: Any) -> None:
    """Emit a single-line JSON log record. Used for intent, SQL, status, timing."""
    record = {"event": event, **fields}
    print(json.dumps(record, default=str), file=sys.stdout, flush=True)
