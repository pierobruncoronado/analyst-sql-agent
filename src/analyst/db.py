"""Read-only query execution against the SELECT-only role.

Defense in depth: the connection uses DATABASE_URL_RO (analyst_ro, SELECT-only),
AND we set the transaction read-only AND a statement_timeout AND cap rows via
fetchmany. These are execution guardrails, not the security layer (schema
validation + destructive rejection come in the security session).
"""

from __future__ import annotations

import psycopg

from .config import Config


def run_readonly(cfg: Config, sql: str) -> tuple[list[str], list[tuple]]:
    """Execute `sql` read-only; return (column names, rows up to row_cap).

    Raises psycopg errors to the caller (the execute node), which records them.
    """
    with psycopg.connect(cfg.database_url_ro) as conn:
        conn.read_only = True  # belt-and-suspenders on top of the RO role
        with conn.cursor() as cur:
            cur.execute(f"SET LOCAL statement_timeout = {int(cfg.statement_timeout_ms)}")
            cur.execute(sql)
            columns = [d.name for d in cur.description] if cur.description else []
            rows = cur.fetchmany(cfg.row_cap)
    return columns, rows
