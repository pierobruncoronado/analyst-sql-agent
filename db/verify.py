"""Verification queries — proof the schema is seeded with real, multi-month data.

Runs read SELECTs and prints results. This is the "show the real output" step.

Usage:
  uv run python db/verify.py
"""

from __future__ import annotations

import os

import psycopg
from dotenv import load_dotenv


COUNTS_SQL = """
SELECT 'customers' AS table, COUNT(*) AS rows FROM customers
UNION ALL SELECT 'products', COUNT(*) FROM products
UNION ALL SELECT 'orders', COUNT(*) FROM orders
UNION ALL SELECT 'order_items', COUNT(*) FROM order_items
ORDER BY table;
"""

DATE_RANGE_SQL = """
SELECT MIN(created_at)::date AS first_order,
       MAX(created_at)::date AS last_order,
       COUNT(DISTINCT date_trunc('month', created_at)) AS distinct_months
FROM orders;
"""

TOP_PRODUCTS_SQL = """
SELECT p.name,
       p.category,
       SUM(oi.quantity * oi.unit_price)::numeric(12,2) AS revenue
FROM order_items oi
JOIN products p ON p.id = oi.product_id
JOIN orders   o ON o.id = oi.order_id
WHERE o.created_at >= date_trunc('month', now()) - interval '1 month'
  AND o.created_at <  date_trunc('month', now())
GROUP BY p.name, p.category
ORDER BY revenue DESC
LIMIT 5;
"""


def _print_table(title: str, cur: psycopg.Cursor) -> None:
    cols = [d.name for d in cur.description]
    rows = cur.fetchall()
    print(f"\n=== {title} ===")
    print(" | ".join(cols))
    print("-" * 60)
    for r in rows:
        print(" | ".join(str(v) for v in r))


def main() -> None:
    load_dotenv()
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL not set. Copy .env.example to .env and fill it in.")

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(COUNTS_SQL)
            _print_table("Row counts per table", cur)
            cur.execute(DATE_RANGE_SQL)
            _print_table("Order date range (must span several months)", cur)
            cur.execute(TOP_PRODUCTS_SQL)
            _print_table("Top 5 products by revenue (last full month)", cur)


if __name__ == "__main__":
    main()
