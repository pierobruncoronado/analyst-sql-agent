"""Seed the sales schema with deterministic synthetic data.

Volume (per CLAUDE.md decision, "medium"):
  ~200 customers, ~50 products, ~5,000 orders over the last 6 months,
  each order with 1-5 line items (~15k order_items).

Determinism: RNG and Faker are seeded with a fixed SEED; NOW_ANCHOR fixes the
date window so per-month counts are identical on every re-run and every clone.
Re-running TRUNCATEs first, so it is idempotent.

Usage:
  uv run python db/seed.py
"""

from __future__ import annotations

import os
import random
from datetime import datetime, timedelta, timezone

import psycopg
from dotenv import load_dotenv
from faker import Faker

SEED = 42
# Fixed anchor — keeps per-month counts identical on every re-run and every clone.
# Changing this date is a breaking change: it shifts per-month counts everywhere.
NOW_ANCHOR = datetime(2026, 6, 16, 0, 0, 0, tzinfo=timezone.utc)

N_CUSTOMERS = 200
N_PRODUCTS = 50
N_ORDERS = 5_000
MONTHS_BACK = 6
MAX_ITEMS_PER_ORDER = 5
MAX_QTY_PER_ITEM = 5

# Weighted so most orders settle (delivered/paid) but enough variety for filters.
STATUS_WEIGHTS = {
    "delivered": 45,
    "paid": 20,
    "shipped": 15,
    "pending": 8,
    "cancelled": 7,
    "refunded": 5,
}

PRODUCT_CATEGORIES = [
    "Electronics", "Home & Kitchen", "Sports", "Books",
    "Toys", "Beauty", "Office", "Garden",
]


def _conn_str() -> str:
    load_dotenv()
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL not set. Copy .env.example to .env and fill it in.")
    return url


def _build_customers(fake: Faker, now: datetime) -> list[tuple]:
    rows = []
    used_emails: set[str] = set()
    for cid in range(1, N_CUSTOMERS + 1):
        name = fake.name()
        # Guarantee unique emails (schema has UNIQUE constraint).
        email = fake.unique.email()
        used_emails.add(email)
        # Customers created somewhere in the last ~year.
        created = now - timedelta(days=random.randint(30, 365), hours=random.randint(0, 23))
        rows.append((cid, name, email, created))
    return rows


def _build_products(fake: Faker) -> list[tuple]:
    rows = []
    for pid in range(1, N_PRODUCTS + 1):
        category = random.choice(PRODUCT_CATEGORIES)
        name = f"{fake.color_name()} {fake.word().capitalize()} {category[:-1] if category.endswith('s') else category}"
        price = round(random.uniform(5, 500), 2)
        rows.append((pid, name, category, price))
    return rows


def _weighted_status() -> str:
    statuses = list(STATUS_WEIGHTS.keys())
    weights = list(STATUS_WEIGHTS.values())
    return random.choices(statuses, weights=weights, k=1)[0]


def _build_orders(now: datetime) -> list[tuple]:
    start = now - timedelta(days=MONTHS_BACK * 30)
    span_seconds = int((now - start).total_seconds())
    rows = []
    for oid in range(1, N_ORDERS + 1):
        customer_id = random.randint(1, N_CUSTOMERS)
        status = _weighted_status()
        created = start + timedelta(seconds=random.randint(0, span_seconds))
        rows.append((oid, customer_id, status, created))
    return rows


def _build_order_items(products: list[tuple]) -> list[tuple]:
    # products row = (id, name, category, price)
    price_by_id = {p[0]: p[3] for p in products}
    rows = []
    item_id = 1
    for order_id in range(1, N_ORDERS + 1):
        n_items = random.randint(1, MAX_ITEMS_PER_ORDER)
        chosen = random.sample(range(1, N_PRODUCTS + 1), k=min(n_items, N_PRODUCTS))
        for product_id in chosen:
            quantity = random.randint(1, MAX_QTY_PER_ITEM)
            unit_price = price_by_id[product_id]
            rows.append((item_id, order_id, product_id, quantity, unit_price))
            item_id += 1
    return rows


def main() -> None:
    random.seed(SEED)
    fake = Faker()
    fake.seed_instance(SEED)

    now = NOW_ANCHOR

    print("Building synthetic data...")
    customers = _build_customers(fake, now)
    products = _build_products(fake)
    orders = _build_orders(now)
    order_items = _build_order_items(products)
    print(
        f"  customers={len(customers)} products={len(products)} "
        f"orders={len(orders)} order_items={len(order_items)}"
    )

    with psycopg.connect(_conn_str()) as conn:
        with conn.cursor() as cur:
            print("Truncating existing data...")
            cur.execute("TRUNCATE order_items, orders, products, customers RESTART IDENTITY CASCADE;")

            print("Inserting customers...")
            cur.executemany(
                "INSERT INTO customers (id, name, email, created_at) VALUES (%s, %s, %s, %s)",
                customers,
            )
            print("Inserting products...")
            cur.executemany(
                "INSERT INTO products (id, name, category, price) VALUES (%s, %s, %s, %s)",
                products,
            )
            print("Inserting orders...")
            cur.executemany(
                "INSERT INTO orders (id, customer_id, status, created_at) VALUES (%s, %s, %s, %s)",
                orders,
            )
            print("Inserting order_items...")
            cur.executemany(
                "INSERT INTO order_items (id, order_id, product_id, quantity, unit_price) "
                "VALUES (%s, %s, %s, %s, %s)",
                order_items,
            )

            # Re-sync identity sequences past the explicit ids we inserted.
            for table in ("customers", "products", "orders", "order_items"):
                cur.execute(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"(SELECT MAX(id) FROM {table}));"
                )
        conn.commit()

    print("Seed complete.")


if __name__ == "__main__":
    main()
