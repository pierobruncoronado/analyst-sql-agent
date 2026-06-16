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

### Blocked on user (external lead-time, browser)
- [ ] Create Supabase project → paste **Session pooler (5432)** `DATABASE_URL` into `.env`.
- [ ] Create + activate Railway account (used later; activate today for lead-time).

### Done once DATABASE_URL is provided
- [ ] `uv sync` (install deps) — *pending verification run*.
- [ ] `uv run python db/apply_schema.py` — create schema.
- [ ] `uv run python db/seed.py` — seed data.
- [ ] `uv run python db/verify.py` — show real counts + date range (acceptance proof).
- [ ] `uv run python db/create_readonly_role.py` — create RO role, fill `DATABASE_URL_RO`.
- [ ] Commit + push to https://github.com/pierobruncoronado/analyst-sql-agent

## Next session (Phase 2 cont.)
- Start the LangGraph state machine: typed graph state + `classify` node (forced tool-use
  enum: answerable / out-of-schema / destructive).
- Wire Anthropic SDK (Haiku default) and the read-only DB execution node.
