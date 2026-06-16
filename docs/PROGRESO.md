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
- [x] `ANTHROPIC_API_KEY` → in `.env` (`.env.example` keeps the placeholder).
      ⚠️ Key was pasted in chat → **rotate it in the Anthropic console** and re-update `.env`.

### Done — Day 2 build (happy path RUNNING end-to-end)
1. [x] Deps `langgraph` + `anthropic` added via uv. Model id / forced tool-use / token shape
       verified against the `claude-api` reference. Project is an installable package
       (hatchling, `src/analyst`) → `uv run python -m analyst "..."` works.
2. [x] Typed `GraphState` (question, intent, sql, columns, rows, answer, error) +
       instrumentation (`latency_ms`, `tokens`) with a merge reducer so nodes accumulate, not overwrite.
3. [x] Support layer: `config.py`, `llm.py`, `db.py`, `schema.py` (fixed-schema constant).
4. [x] Nodes: classify (forced-tool, log-only), generate_sql (forced-tool `emit_sql`),
       execute_sql (RO + timeout + fetchmany cap), synthesize (Haiku, grounded). Structured JSON logs.
5. [x] LangGraph `StateGraph`, linear: classify → generate_sql → execute_sql → synthesize → END.
6. [x] CLI runner `src/analyst/__main__.py`, fail-closed on empty input.
7. [x] Real runs shown (ES count + EN top-N JOIN), both grounded on real data. `ruff` clean.
       Meets spec §8 first criterion. DECISIONS + PROGRESO updated; committed + pushed.

## Phase 2 — Day 3 (next session): the self-correction LOOP + security
Goal: add the conditional/cyclic edges — the thing the project exists to demonstrate.
START HERE:
1. [ ] Conditional edge on `intent`: `out_of_schema` / `destructive` → reject branch (honest
       message, no SQL run). This activates the classifier that's currently log-only.
2. [ ] Self-correction cycle: `execute_sql` error → `diagnose` node → back to `generate_sql`,
       capped at 3 cycles. Track cycle count + error text in state. This is the LangGraph delta.
3. [ ] Security layer (defense beyond the RO role): validate generated SQL stays within the 4
       tables + is a single SELECT (reject DDL/DML/multi-statement) before execution.
4. [ ] Anti-hallucination: prove the "no cost column → margin not derivable" path returns an honest
       "can't compute" instead of inventing numbers.
5. [ ] Demonstrate the loop recovering from at least one real SQL error (spec §8 criterion 2).

### Carry-over note for the loop session
- Latent gotcha to turn into an eval case: `generate_sql` produced `EXTRACT(MONTH FROM created_at)=5`
  with no year filter (fine on current seed, wrong across years). See DECISIONS Day-2 build.
