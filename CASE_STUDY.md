# Case Study — Analyst: Conversational SQL Agent

> **Live:** `https://analyst-sql-agent-production.up.railway.app`

---

## 1. Problem

Business teams ask ad-hoc data questions in Slack, then wait hours for an analyst to write a query. The bottleneck is not the query — it is the handoff. A conversational SQL agent eliminates the handoff for the class of questions that can be answered from a known schema.

The technical gap I wanted to close: most "NL→SQL" demos use a single prompt → one shot → print result. They skip the part that matters in production — **what happens when the SQL fails?** Haiku regularly generates wrong SQL for window functions, ambiguous date filters, or CTEs. Without a recovery loop, any error surfaces as a crash or a confusing error message.

This project builds the full production path: classify intent → generate SQL → execute → **auto-correct on DB error → retry** → synthesize — as a typed LangGraph state machine.

---

## 2. What I Built

A FastAPI service that takes a plain-language question (ES or EN), routes it through a LangGraph state machine, executes read-only SQL against a Postgres database, and returns a grounded answer. The core behavior:

- **Happy path:** question → SQL → result → natural-language answer in the question's language
- **Self-correction loop:** DB error → LLM diagnoses the error → regenerates SQL → retries, up to 3 cycles. If all fail: honest decline.
- **Security gate:** destructive or out-of-schema questions are rejected by a deterministic node before any SQL runs, using three independent read-only layers.
- **Anti-hallucination:** questions that cannot be answered from the schema ("what is my profit margin?") are classified and rejected — no invented numbers.

**Stack:** Python · uv · LangGraph · Anthropic SDK (Haiku 4.5) · Postgres/Supabase · psycopg3 · FastAPI · slowapi · Railway

---

## 3. Architecture

```
User question (ES/EN)
        │
        ▼
  FastAPI POST /ask
  slowapi: 10 req/min/IP
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  LangGraph StateGraph                                   │
│                                                         │
│  ┌──────────┐  out_of_schema  ┌─────────┐              │
│  │ classify │─────────────────► reject  ├──► answer    │
│  └────┬─────┘  destructive    └─────────┘              │
│       │ answerable         (fixed template, 0 LLM calls)│
│       ▼                                                 │
│  ┌──────────────┐                                       │
│  │ generate_sql │◄──────────────────────┐               │
│  └──────┬───────┘  (retries with        │               │
│         │           diagnosis injected) │               │
│         ▼                               │               │
│  ┌──────────────┐  error + cycle < 3   ┌┴──────────┐   │
│  │ execute_sql  │──────────────────────► diagnose   │   │
│  └──────┬───────┘                      └───────────┘   │
│         │ success (or cycle == 3 → honest decline)      │
│         ▼                                               │
│  ┌──────────────┐                                       │
│  │  synthesize  ├──► grounded answer (same language)    │
│  └──────────────┘                                       │
└─────────────────────────────────────────────────────────┘
```

**State:** typed `GraphState` TypedDict. Every node writes to its own keys; `latency_ms` and `tokens` use a merge reducer (`Annotated[dict, _merge]`) so each stage accumulates without overwriting.

**Forced tool-use:** both `classify` and `generate_sql` use `tool_choice={"type":"tool","name":"<tool>"}` — the model must emit a valid enum or a SQL string. No free-text parsing.

**Cycle back-edge:** `diagnose → generate_sql` is the graph's only back-edge. `_route_execute` reads `cycle_count` and `error` to decide: synthesize (success), diagnose (error + headroom), or synthesize with honest decline (error + cap reached).

---

## 4. Results

### Story 1 — Self-correction loop in action

On the month-over-month revenue question, Haiku generated:

```sql
SELECT DATE_TRUNC('month', created_at) AS month,
       SUM(oi.quantity * oi.unit_price) AS revenue,
       revenue - LAG(revenue) OVER (ORDER BY month) AS mom_change  -- ← column alias in WHERE
FROM orders o JOIN order_items oi ON ...
GROUP BY month ORDER BY month
```

Postgres returned: `column "revenue" does not exist` (column alias not reachable in the same SELECT level).

The `diagnose` node read the raw DB error and the failed SQL, produced a 2-sentence diagnosis, and injected it into the next `generate_sql` prompt. Cycle 1 returned a correct CTE that Postgres accepted. The agent answered with 6 months of revenue + month-over-month differences.

**Result:** recovered from a real DB error in 1 correction cycle. The loop mechanic is the point.

### Story 2 — Co-location: 15× DB query improvement

| Environment | `execute_sql` latency |
|---|---|
| Local laptop → Supabase us-west-1 | ~1 550 ms |
| Railway us-west-1 → Supabase us-west-1 | ~101 ms |

15× faster. The decision was made on Day 1 before any code: deploy compute in the same region as the database. A prior project placed compute in US East against a São Paulo database — 3.5 s of cross-region overhead per query. Measuring this explicitly (structured latency logs per stage) is what lets you see it rather than hand-wave "it's fast now."

### Story 3 — Security: three independent read-only layers

A single `DROP TABLE customers` request reaches three independent barriers:

| Layer | Mechanism | What breaks if removed |
|---|---|---|
| **DB role** | `analyst_ro` (Postgres) has only `SELECT` granted | Write query returns `permission denied` at DB level |
| **No admin credential** | Container holds only `DATABASE_URL_RO` + `ANTHROPIC_API_KEY` | Even with code execution, no write-capable credential to use |
| **Config guard** | `config.py` crashes at startup if `DATABASE_URL_RO` missing but `DATABASE_URL` present | Prevents accidental admin-credential redeploy |

The `reject` node (for `destructive` + `out_of_schema` intents) calls zero LLM endpoints — a destructive question is blocked before the model sees it. This closes the OWASP LLM Top 10 prompt-injection → SQL-injection path at the classifier level, not inside the prompt.

### Story 4 — Eval suite as a gate, not an afterthought

Baseline (Haiku 4.5, 2026-06-16):

| Metric | Value |
|---|---|
| Hard assertions | 7 / 7 passed |
| LLM-as-judge | 3 / 3 scored 1 |
| Suite cost | $0.0170 / run |
| Suite time | 21.2 s |
| Canonical May count | 852 orders (fixed-anchor seed, confirmed live) |

The 7 cases cover: happy-path count (with year-guard SQL assertion), top-N JOIN, MoM revenue, anti-hallucination (margin question → `out_of_schema`), off-topic redirect, SQL-literal injection, natural-language injection.

11 deterministic unit tests (2.35 s, no API/DB calls) use a `_FakeLLM` duck type and `patch("analyst.nodes.run_readonly")` to prove the loop mechanic — 3-cycle exhaustion, recovery on cycle 1, cycle count increments per `diagnose` call. Both suites run in CI on every push.

---

## 5. Decisions & Trade-offs

**Haiku over Sonnet:** chose the cheapest model first. Baseline: 7/7 at $0.017/suite. Sonnet would cost ~15× more per call. The eval data, not intuition, is the upgrade trigger.

**Reject node: fixed template, zero LLM calls:** adds ~0 ms and 0 tokens on the rejection path. A destructive question should never reach the model — that is the security property. Free-text generation on the rejection path would add latency, cost, and non-determinism to a path that needs none of those.

**LangGraph over manual if/else:** the back-edge (`diagnose → generate_sql`) and state accumulation are the main reasons. LangGraph makes the cycle explicit in the graph definition, makes state typed, and makes each node single-responsibility. The alternative is a while loop with shared mutable dict — harder to test, harder to intrument.

**`200` for all agent responses, `422` only for malformed input:** an `out_of_schema` or `destructive` rejection is a valid, expected agent response — not an HTTP error. Returning 4xx for intentional rejections would confuse clients that need to display the rejection message.

**Session pooler, port 5432:** Supabase's direct connection is IPv6-only and fails from Railway/Docker. The transaction pooler (6543) breaks prepared statements (psycopg3 uses them by default). Session pooler (5432, IPv4) is the only option that works end-to-end.

**`NOW_ANCHOR` in seed.py:** fixing a date anchor ensures every clone that runs `db/seed.py` produces the same per-month counts. Without it, the May count changes daily and the eval assertion on "852 orders in May" would drift. Tradeoff: relative queries ("last 90 days") in the seed data are anchored to 2026-06-16, not today — acceptable for a fixed synthetic schema.

---

## 6. What v2 Would Add

| Feature | Why deferred |
|---|---|
| Multi-turn memory (conversation context) | Requires session state; adds scope to every node; deliberate v2 boundary |
| Auth + multi-tenant | Each tenant = different schema or RLS policy; changes the connection model |
| Charting / visualizations | Frontend scope; the core is the SQL loop, not the render layer |
| Arbitrary schema upload | Requires schema introspection, embedding, and retrieval — a project of its own |
| Fine-tuning | No labeled dataset yet; evals first, fine-tuning if the eval gap justifies it |

---

## 7. Honest Scope

This is a v1 proof-of-concept over a **fixed, synthetic schema** of four tables. The LangGraph self-correction loop is the engineering claim and the thing that can be measured — the eval suite measures it. Everything else (FastAPI wrapper, Railway deploy, rate limiting, security layers) is production scaffolding around that core.

What it does not do: multi-database routing, dynamic schema discovery, auth/access control, production-grade error budgets, or multi-turn conversation memory. Those are explicit v2 items, not omissions.

The 852-order canonical count and the 15× co-location improvement are real numbers from real runs, not estimates.
