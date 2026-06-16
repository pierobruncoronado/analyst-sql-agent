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
- [ ] **Railway account create + activate** — still pending on user (used later; activate for lead-time).

### DB applied + verified (real output)
- [x] `uv sync` — venv built, deps installed.
- [x] `db/apply_schema.py` — schema applied to Supabase.
- [x] `db/seed.py` — 200 customers / 50 products / 5,000 orders / 15,164 order_items.
- [x] `db/verify.py` — counts OK; order range 2025-12-18 → 2026-06-16 (7 calendar months);
      top-5-by-revenue JOIN query works.
- [x] `db/create_readonly_role.py` — `analyst_ro` created; `DATABASE_URL_RO` in `.env`.
- [x] `db/check_readonly.py` — SELECT ok, INSERT denied → read-only proven.
- [x] Second commit + push to https://github.com/pierobruncoronado/analyst-sql-agent

## Next session (Phase 2 cont.)
- Start the LangGraph state machine: typed graph state + `classify` node (forced tool-use
  enum: answerable / out-of-schema / destructive).
- Wire Anthropic SDK (Haiku default) and the read-only DB execution node.
