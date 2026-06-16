"""Prove the read-only role is read-only at the connection layer.

Connects as DATABASE_URL_RO and asserts: SELECT works, INSERT is denied.
This is the security evidence for "read-only in depth" (spec.md §3).

Usage:
  uv run python db/check_readonly.py
"""

from __future__ import annotations

import os

import psycopg
from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    url = os.getenv("DATABASE_URL_RO")
    if not url:
        raise SystemExit("DATABASE_URL_RO not set in .env.")

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_user, COUNT(*) FROM customers")
            user, n = cur.fetchone()
            print(f"SELECT ok  -> connected as '{user}', customers={n}")

            try:
                cur.execute("INSERT INTO customers (name, email) VALUES ('x', 'x@example.com')")
                conn.commit()
                raise SystemExit("FAIL: INSERT succeeded — role is NOT read-only!")
            except psycopg.errors.InsufficientPrivilege as e:
                conn.rollback()
                print(f"INSERT denied -> {str(e).strip().splitlines()[0]}")

    print("PASS: connection is read-only.")


if __name__ == "__main__":
    main()
