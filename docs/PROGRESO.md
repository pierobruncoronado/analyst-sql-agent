# PROGRESO — Analyst

## Phase 2 — Day 1 (in progress)
Goal: repo + Python env + folder structure; sales schema seeded in Supabase with
several months of synthetic data, verifiable with a real SELECT; external
lead-time accounts (Supabase + Railway) activated today.

### Done (local scaffold)
- [x] `uv` installed; `pyproject.toml` with Phase-2 deps (psycopg3, python-dotenv, faker).
- [x] Folder structure: `db/`, `docs/`, `src/analyst/`, `tests/`, `evals/`.
- [x] `.gitignore` (+ `.env` excluded), `.env.example`, `README.md`.
- [x] `db/schema.sql` (4 fixed tables, FKs, indexes).
- [x] `db/seed.py` (deterministic, medium volume), `db/apply_schema.py`, `db/verify.py`.
- [x] `db/create_readonly_role.py` (SELECT-only role + derived RO URL).
- [x] Renamed spec to `docs/spec.md`; `docs/DECISIONS.md` started.

### External lead-time
- [x] Supabase project created (us-west-1) → `DATABASE_URL` (Session pooler 5432) in `.env`.
- [x] **Railway account created + activated** (via GitHub) — done Day 2; used later for deploy.

### DB applied + verified (real output)
- [x] `uv sync` — venv built, deps installed.
- [x] `db/apply_schema.py` — schema applied to Supabase.
- [x] `db/seed.py` — 200 customers / 50 products / 5,000 orders / 15,164 order_items.
- [x] `db/verify.py` — counts OK; order range 2025-12-18 → 2026-06-16 (7 calendar months);
      top-5-by-revenue JOIN query works.
- [x] `db/create_readonly_role.py` — `analyst_ro` created; `DATABASE_URL_RO` in `.env`.
- [x] `db/check_readonly.py` — SELECT ok, INSERT denied → read-only proven.
- [x] Second commit + push to https://github.com/pierobruncoronado/analyst-sql-agent

## Phase 2 — Day 2 (planning only; NO code written)
Goal for the session: minimal LangGraph **happy path** running end-to-end —
NL question → classify (forced tool-use enum) → generate SQL → execute read-only
against `DATABASE_URL_RO` → synthesize answer. NO self-correction loop, NO security
reject branches yet (those are next session). "Minimal and RUNNING before the loop."

### Settled this session (carry into next, do not re-litigate)
- [x] Plan of 7 steps approved (below).
- [x] Decision: **classify is linear, log-only** — runs forced tool-use, logs the intent,
      graph proceeds straight to generate_sql regardless. Conditional/reject branch = next session.
- [x] Decision: **synthesis via LLM (Haiku)** — a 3rd Haiku call writes the answer sentence in
      the question's language (ES/EN). Cost/latency measured.
- [x] Decision: **execution guardrails now** — `statement_timeout` + row cap via `fetchmany`
      in the execute node (these are execution concerns, not reject branches). Schema validation
      + destructive rejection still deferred to the security session.

### Blocked on user (needed to run end-to-end)
- [ ] `ANTHROPIC_API_KEY` → goes into `.env` only (`.env.example` keeps the placeholder).

### Pending — execute next session, START AT STEP 1
1. [ ] Add deps `langgraph` + `anthropic` via uv. Verify Haiku 4.5 model id + forced tool-use
       (`tool_choice`) + token-count shape against the `claude-api` reference (don't assume).
       Make the project an installable package (hatchling, `src/analyst` layout) so
       `uv run python -m analyst "..."` works.
2. [ ] Typed graph state (TypedDict): question, intent, sql, rows, columns, answer +
       instrumentation (per-stage latency_ms, per-call tokens).
3. [ ] Support layer in `src/analyst/`: `config.py` (env, model id, row cap, timeout),
       `llm.py` (Anthropic client + forced tool-use helper + token capture),
       `db.py` (read-only exec vs `DATABASE_URL_RO`, statement_timeout, fetchmany cap),
       fixed-schema description constant for prompts.
4. [ ] Nodes (one responsibility each): classify, generate_sql, execute_sql, synthesize.
       Structured JSON logs, one line per event (intent, final SQL, status, per-stage latency, tokens).
5. [ ] LangGraph `StateGraph`, **linear**: classify → generate_sql → execute_sql → synthesize → END.
6. [ ] CLI runner `src/analyst/__main__.py`: `uv run python -m analyst "<question>"`.
7. [ ] Run a real question end-to-end (e.g. "¿cuántos pedidos hubo en mayo?"), show real output
       (intent, SQL, rows, synthesized answer, per-stage latency, tokens). Verify vs spec §8,
       update DECISIONS + PROGRESO, commit + push.
