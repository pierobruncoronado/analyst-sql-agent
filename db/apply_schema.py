"""Apply db/schema.sql to the database in DATABASE_URL.

Usage:
  uv run python db/apply_schema.py
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def main() -> None:
    load_dotenv()
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL not set. Copy .env.example to .env and fill it in.")

    ddl = SCHEMA_PATH.read_text(encoding="utf-8")
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
        conn.commit()
    print(f"Applied {SCHEMA_PATH.name} successfully.")


if __name__ == "__main__":
    main()
