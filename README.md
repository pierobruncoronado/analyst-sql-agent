# Analyst — Conversational SQL Agent

Ask business questions in natural language (ES/EN); get answers from real data.
Analyst turns a question into **read-only** SQL over a fixed sales schema, runs
it, and explains the result — with a **LangGraph self-correction loop** that
reads DB errors, diagnoses them, and retries (max 3 cycles).

> Status: **Phase 2 (build core) — infra + seeded schema.** The agent graph,
> security layer, and API land in later phases. See `docs/spec.md`.

## Why this exists
Owners and non-technical teams can't answer questions about their own data
without SQL or a rigid dashboard. Analyst lets anyone ask in their own language
and get the correct answer from live data — safely (SELECT-only at the
connection layer, schema validation, no hallucinated numbers).

## Schema (fixed, v1)
`customers` · `products` · `orders` · `order_items` — synthetic data seeded over
~6 months. Definition in `db/schema.sql`.

## Stack
Python · uv · Postgres (Supabase) · psycopg3 · Faker (seed) — LangGraph +
Anthropic SDK + FastAPI added in later phases.

## Setup
Requires [uv](https://docs.astral.sh/uv/) and a Supabase Postgres project.

```bash
# 1. Install dependencies into a managed venv
uv sync

# 2. Configure credentials
cp .env.example .env        # then fill in DATABASE_URL (Supabase SESSION pooler, port 5432)

# 3. Create schema, seed data, and verify
uv run python db/apply_schema.py
uv run python db/seed.py
uv run python db/verify.py

# 4. (Security) create the SELECT-only role the agent will use at runtime
#    Set ANALYST_RO_PASSWORD in .env first, then:
uv run python db/create_readonly_role.py   # prints DATABASE_URL_RO to paste back into .env
```

## Project layout
```
db/      schema DDL, deterministic seed, verification, read-only role setup
docs/    spec.md (source of truth), DECISIONS.md, PROGRESO.md
src/     analyst/ — agent graph (later phases)
evals/   golden eval suite (later phases)
tests/   unit/integration tests
```

## Docs
- `docs/spec.md` — full specification (source of truth).
- `docs/DECISIONS.md` — decisions log (what / why / how).
- `docs/PROGRESO.md` — running status and next-session TODOs.
