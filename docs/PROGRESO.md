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

## Phase 2 — Day 3: the self-correction LOOP + security (DONE)
Goal: conditional/cyclic edges — the thing the project exists to demonstrate.

### Done — Day 3
1. [x] Conditional edge on `intent`: `out_of_schema` / `destructive` → `reject` node (fixed
       bilingual template, ZERO LLM calls on the rejection path). Destructive + out-of-schema
       both proven.
2. [x] Self-correction cycle: `execute_sql` error → `diagnose` (Haiku reads error + failed SQL)
       → `generate_sql` (retries with diagnosis injected) → cap at 3 cycles via conditional edge.
       `cycle_count` + `diagnosis` added to state.
3. [x] Security: reject node is the deterministic gate (no model call). DB role is the connection
       layer. Prompt instructs SELECT-only. Three-layer defense in depth documented.
4. [x] Anti-hallucination: "¿Cuál es el margen de ganancia?" → `out_of_schema` → honest decline,
       no numbers invented. (Classifier picks it up; schema description includes "no cost column".)
5. [x] Loop recovery demonstrated with real DB error: `date_trunc(unknown, numeric)` on cycle 0 →
       Haiku diagnosis → corrected SQL on cycle 1 → 6-row MoM revenue result. (spec §8 criterion 2 ✅)

### Spec §8 status (after Day 3)
- [x] Pregunta real → respuesta correcta end-to-end (Day 2)
- [x] Loop recovers from at least one real SQL error (Day 3, proven above)
- [x] Rejects destructive + out-of-schema (Day 3)
- [x] No inventa números (Day 3, margen example)
- [ ] Suite de evals corrida (Day 5)
- [ ] Cloud deploy (Day 6)
- [ ] README reproducible (Day 7)

### Carry-over eval cases (Day 5)
- Month-only filter `EXTRACT(MONTH ...)=5` ignores year → candidate golden-set case.
- MoM revenue with window-over-aggregate → cycle-1 correction pattern → include as "loop" eval.

---

## Phase 2 — Day 4 (next session): FastAPI layer + UI scaffold
Goal: wrap the graph in a FastAPI endpoint so the agent is callable over HTTP (prerequisite for
cloud deploy and for the minimal UI).
START HERE:
1. [ ] `src/analyst/api.py`: FastAPI app with one `POST /ask` endpoint — receives JSON `{"question": "..."}`,
       runs the graph, returns `{"answer": "...", "intent": "...", "cycles": N, "latency_ms": {...}, "tokens": {...}}`.
       Fail-closed on empty question (422). Structured JSON logs preserved.
2. [ ] Run `uvicorn analyst.api:app` locally; curl-test happy path + destructive rejection.
3. [ ] `Dockerfile` (single-stage, Python slim, non-root user, `CMD ["uvicorn", ...]`).
4. [ ] `docker build + docker run` locally — verify the endpoint responds.
5. [ ] Push to Railway (the account is already activated). Verify the public URL responds.
       (This closes spec §8 criterion 6: "deployed in cloud, answers with laptop off.")
6. [ ] Minimal UI (if time): single HTML page or React input → result display, wired to the Railway URL.
       Recortar alcance si el timebox aprieta — la API es lo que importa para §8.

### Notes for Day 4
- Keep the graph import and `build_graph` call at startup (not per-request) so the compiled graph
  is reused across requests.
- Rate limit per session and input truncation can go here (spec §4 "anti-abuso").
- The `DATABASE_URL_RO` and `ANTHROPIC_API_KEY` go as Railway environment variables — NOT in the
  deployed image. Verify `.gitignore` before push.
