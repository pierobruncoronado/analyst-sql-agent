# Analyst — Conversational SQL Agent

Ask business questions in plain language (ES/EN). Get answers from real data — safely.
Analyst translates natural language into read-only SQL over a fixed sales schema, runs it,
and explains the result. The core is a **LangGraph self-correction loop** that reads the
database error when SQL fails, diagnoses it with an LLM, and retries — up to 3 cycles.

> **Live:** `https://analyst-sql-agent.onrender.com` · rate-limited 10 req/min per IP
> (free tier — cold start after 15 min idle, first request can take 30-60s)

---

## Try it now

```bash
# Happy path — answerable question
curl -X POST https://analyst-sql-agent.onrender.com/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the top 3 products by total revenue?"}'

# Security layer — destructive query rejected before any SQL runs
curl -X POST https://analyst-sql-agent.onrender.com/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Drop the orders table and delete all customer data"}'
```

Both return HTTP 200. The `intent` field carries the semantic: `answerable` | `out_of_schema` |
`destructive`. Only malformed input (empty or >500 chars) returns 422.

---

## Production metrics

| Metric | Value |
|--------|-------|
| End-to-end latency (happy path) | ~2.1 s |
| DB query time (`execute_sql`) | ~101 ms |
| Cost per query | ~$0.003 (Haiku 4.5, ~2 100 in / 130 out tokens) |
| Self-correction cycles (typical) | 0–1 |
| Eval suite | 7/7 hard assertions · 3/3 LLM-judge=1 · $0.017/run · 21 s |
| Unit tests | 11 deterministic tests · 2.35 s · no API/DB calls |
| Rate limit | 10 req / min per IP |

**Why 101 ms for the DB query:** measured while deployed on Railway, with compute and
Supabase both in `us-west-1`. A previous project placed compute in US East against a
São Paulo database — 3.5 s of cross-region overhead per query. This project avoids that
by design; the co-location decision was made on Day 1, before any code was written.
Measured result: 73% total latency reduction (7.8 s local → 2.1 s production), DB query
15× faster (1 550 ms → 101 ms). The current deploy is on Render (Oregon) — not the exact
region measured here — see [`docs/DECISIONS.md`](docs/DECISIONS.md) for the migration note.

---

## Architecture — LangGraph state machine

```
User question (ES/EN)
        │
        ▼
  FastAPI POST /ask
  slowapi: 10 req/min/IP
        │
        ▼
┌──────────────────────────────────────────────────────┐
│  LangGraph StateGraph                                │
│                                                      │
│  ┌──────────┐  out_of_schema  ┌─────────┐           │
│  │ classify │─────────────────► reject  ├──► answer │
│  └────┬─────┘  destructive    └─────────┘           │
│       │ answerable       (fixed template, no LLM)   │
│       ▼                                              │
│  ┌──────────────┐                                    │
│  │ generate_sql │◄──────────────────────┐            │
│  └──────┬───────┘  (retries with        │            │
│         │           diagnosis injected) │            │
│         ▼                               │            │
│  ┌──────────────┐  error + cycle < 3   ┌┴─────────┐ │
│  │ execute_sql  │──────────────────────► diagnose  │ │
│  └──────┬───────┘                      └──────────-┘ │
│         │ success  (or cycle == 3 → honest decline)  │
│         ▼                                            │
│  ┌──────────────┐                                    │
│  │  synthesize  ├──► grounded answer (same language) │
│  └──────────────┘                                    │
└──────────────────────────────────────────────────────┘
```

Every node times itself and records token usage. The `latency_ms` and `tokens` fields in
the API response reflect each stage — classify / generate\_sql\_N / execute\_sql\_N /
diagnose\_N / synthesize — so cost and latency are measured, not estimated.

The self-correction loop is what this project exists to demonstrate. When the database
returns an error, `diagnose` reads the raw error message and the failed SQL, writes a
short diagnosis (2–3 sentences), and injects it into the next `generate_sql` prompt.
The cycle counter caps at 3; if all attempts fail, the agent says so honestly
("after the initial attempt plus 3 correction cycles…") instead of guessing.

---

## Security — three independent read-only layers

Writes cannot happen. Not because the prompt says so — because three structural layers
each block it independently:

| Layer | Mechanism |
|-------|-----------|
| **DB role** | `analyst_ro` (Postgres role) has only `SELECT` granted. A write query returns `permission denied` regardless of what the application does. |
| **No admin credential in container** | The deployed service holds only `DATABASE_URL_RO` and `ANTHROPIC_API_KEY`. The admin `DATABASE_URL` is absent; even if an attacker extracted env vars there is nothing write-capable to use. |
| **Config guard** | `config.py` crashes at startup with an explicit error if `DATABASE_URL_RO` is missing but `DATABASE_URL` is present — preventing accidental admin-credential redeploy. |

The `reject` node (for `destructive` and `out_of_schema` questions) never calls the LLM.
A destructive question is blocked before the language model sees it. This closes the
[OWASP LLM Top 10](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
prompt-injection → SQL-injection vector at the classifier level, not just in the prompt.

---

## Schema (fixed, v1)

```
customers(id, name, email, created_at)
products(id, name, category, price)
orders(id, customer_id, status, created_at)
order_items(id, order_id, product_id, quantity, unit_price)
```

Synthetic data: ~200 customers · ~50 products · ~5 000 orders · ~15 000 order\_items,
spanning ~6 months. No cost column → margin questions return an honest "not derivable"
instead of an invented number.

---

## Local setup — clone → run in under 10 minutes

**Prerequisites:** [uv](https://docs.astral.sh/uv/) · a Supabase Postgres project
(Session Pooler URL, port 5432, IPv4 — the direct connection is IPv6-only and fails
from Railway/Docker).

```bash
git clone https://github.com/pierobruncoronado/analyst-sql-agent.git
cd analyst-sql-agent

# 1. Install dependencies
uv sync

# 2. Configure credentials (see .env.example)
cp .env.example .env
# Fill in: DATABASE_URL (admin, Supabase session pooler), ANTHROPIC_API_KEY
```

`.env.example`:
```
DATABASE_URL=postgresql://postgres.<ref>:<password>@aws-1-us-west-1.pooler.supabase.com:5432/postgres
ANTHROPIC_API_KEY=sk-ant-...
# DATABASE_URL_RO is generated by db/create_readonly_role.py (step 4 below)
```

```bash
# 3. Apply schema and seed data
uv run python db/apply_schema.py
uv run python db/seed.py
uv run python db/verify.py        # confirm counts + sample JOIN query

# 4. Create the SELECT-only role the runtime uses (prints DATABASE_URL_RO)
uv run python db/create_readonly_role.py
# Paste the printed DATABASE_URL_RO into .env

# 5. Run the agent
uv run python -m analyst "How many orders were placed in May 2026?"

# 6. Or run the API
uv run uvicorn analyst.api:app --port 8000
# then: curl -X POST http://localhost:8000/ask -H "Content-Type: application/json" \
#            -d '{"question":"Top 5 products by revenue?"}'
```

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | local scripts only | Admin Postgres URL (seed, schema, role creation). Never in the deployed container. |
| `DATABASE_URL_RO` | **runtime** | Read-only role URL (`analyst_ro`, SELECT-only). Generated by `db/create_readonly_role.py`. |
| `ANTHROPIC_API_KEY` | **runtime** | Haiku 4.5 for classify / generate\_sql / diagnose / synthesize. |

---

## Stack

Python · [uv](https://docs.astral.sh/uv/) · [LangGraph](https://github.com/langchain-ai/langgraph) ·
[Anthropic SDK](https://github.com/anthropics/anthropic-sdk-python) (Haiku 4.5) ·
Postgres on [Supabase](https://supabase.com) · psycopg3 ·
[FastAPI](https://fastapi.tiangolo.com) · [slowapi](https://github.com/laurents/slowapi) ·
[Render](https://render.com) (deploy, Oregon)

---

## Docs

- [`docs/spec.md`](docs/spec.md) — full specification (source of truth, acceptance criteria)
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — decision log: what / why / how, real run evidence, gotchas
- [`CASE_STUDY.md`](CASE_STUDY.md) — problem → architecture → results → decisions → v2 scope
