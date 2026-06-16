"""The fixed schema, described for the LLM prompts.

This is the ONLY schema the agent knows about (spec §6). Kept in sync with
db/schema.sql by hand — it's four small tables and won't change in v1.
"""

SCHEMA_DESCRIPTION = """\
Postgres database. Read-only. These are the ONLY tables and columns that exist:

customers(id BIGINT PK, name TEXT, email TEXT, created_at TIMESTAMPTZ)
products(id BIGINT PK, name TEXT, category TEXT, price NUMERIC(10,2))
orders(id BIGINT PK, customer_id BIGINT -> customers.id, status TEXT, created_at TIMESTAMPTZ)
order_items(id BIGINT PK, order_id BIGINT -> orders.id, product_id BIGINT -> products.id,
            quantity INTEGER, unit_price NUMERIC(10,2))

Notes:
- orders.status is one of: 'pending', 'paid', 'shipped', 'delivered', 'cancelled', 'refunded'.
- Line-item revenue is order_items.quantity * order_items.unit_price.
- There is NO cost column anywhere, so profit/margin is NOT derivable from this data.
- "now" relative questions ("last month", "last 90 days") should use now()/CURRENT_DATE.
"""
