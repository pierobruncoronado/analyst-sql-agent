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

## Phase 2 — Day 4: FastAPI + Dockerfile + Railway deploy (DONE)
Goal: agent deployed and running 24/7 in Railway, callable over HTTP.

### Done — Day 4
1. [x] `src/analyst/api.py`: FastAPI app — `POST /ask` (graph compiled once at startup lifespan,
       sync def → threadpool), `GET /` health check, slowapi 10 req/min per IP (spec anti-abuso),
       CORS wildcard, Pydantic 422 on empty/<1/>500-char input, 200 on all agent responses.
2. [x] Local smoke test: health OK, happy path (856 orders May 2026) OK, destructive reject OK,
       empty question → 422 OK.
3. [x] `Dockerfile`: `ghcr.io/astral-sh/uv:python3.11-bookworm-slim`, two-step uv sync for layer
       cache, non-root `appuser`, shell-form CMD for `${PORT:-8000}` expansion.
4. [x] `.dockerignore`: excludes `.env`, `.venv`, `.git`, `db/`, `docs/`, `tests/`, `evals/`.
5. [x] Railway deploy: service Online in US West region (co-located with Supabase us-west-1).
       Public URL: `https://analyst-sql-agent-production.up.railway.app`
6. [x] Live verification (local uvicorn OFF):
       - `POST /ask "How many orders in May 2026?"` → 200, intent=answerable, "856 orders", 2.1s total
         (classify 653 / gen 801 / exec **101ms** / synth 568 ms) — co-location confirmed: exec was
         1550ms local, 101ms on Railway in same region as Supabase.
       - `POST /ask "Drop the orders table..."` → 200, intent=destructive, sql=null, 0ms reject ✓
7. [x] Security hardening: `DATABASE_URL` (admin) removed from Railway env vars. Container holds
       ONLY `DATABASE_URL_RO` + `ANTHROPIC_API_KEY`. `config.py` now has an explicit guard: if
       `DATABASE_URL_RO` is missing but `DATABASE_URL` is present → startup crash with a clear
       error naming the misconfiguration (no silent fallback to admin creds).
8. [x] Verified with laptop-off that service responds using only the read-only credential.
       Spec §8 criterion 6 ✓

### Spec §8 status (after Day 4)
- [x] Pregunta real → respuesta correcta end-to-end (Day 2)
- [x] Loop recovers from at least one real SQL error (Day 3)
- [x] Rejects destructive + out-of-schema (Day 3)
- [x] No inventa números (Day 3)
- [ ] Suite de evals corrida (Day 5)
- [x] Deployed in cloud, answers with laptop off (Day 4) ← NEW
- [ ] README reproducible (Day 7)

### Production metrics (Railway, US West, Haiku)
- Happy path: ~2.1s total (vs ~7.8s local) — 73% faster due to co-location
- Execute_sql: 101ms (vs 1550ms local) — 15× faster, co-location payoff
- Cost per query: ~2093 in / ~127 out tokens → ~$0.0021 + ~$0.00064 ≈ **$0.003/query**

---

## Phase 2 — Day 5: eval suite + CI gate (DONE)
Goal: golden-set evals running with baseline documented; spec §8 criterion 5.

### Done — Day 5
1. [x] `evals/cases.py`: 7 EvalCase objects (5 golden spec §7 + 2 injection variants).
2. [x] `evals/judge.py`: LLM-as-judge, Haiku, 0/1 score, harness error → -1.
3. [x] `evals/run.py`: harness — builds graph once, runs all cases, prints table report,
       exit 0/1 for CI. Soft assertions (cycles_soft_min) do not affect exit code.
4. [x] Month-filter fix: added year-guard instruction to SCHEMA_DESCRIPTION. Eval asserts
       `"YEAR" in sql` for the happy_count case. Baseline confirmed guard is present.
5. [x] `tests/test_loop.py`: 11 deterministic unit tests (no API/DB). Tests routing
       functions + full-graph mechanics (3-cycle exhaustion, recovery, cycle_count increment).
       All 11 pass in 2.35s.
6. [x] `.github/workflows/ci.yml`: two-job CI — unit-tests (no secrets) then evals
       (DATABASE_URL_RO + ANTHROPIC_API_KEY secrets). Evals gate on all 7 hard assertions.
7. [x] Baseline run: 7/7 hard assertions passed, 3/3 judge=1, $0.0170, 21.2s.
       Threshold set at 7/7 after seeing baseline (not before). Spec §8 criterion 5 ✓

### Spec §8 status (after Day 5)
- [x] Pregunta real → respuesta correcta end-to-end (Day 2)
- [x] Loop recovers from at least one real SQL error (Day 3)
- [x] Rejects destructive + out-of-schema (Day 3)
- [x] No inventa números (Day 3)
- [x] Suite de evals corrida: 7/7, baseline documentado, costo medido (Day 5) ← NEW
- [x] Deployed in cloud, answers with laptop off (Day 4)
- [ ] README reproducible — README is updated (Day 4), pending "clonar → correr" final check

### Action required before first CI run
Add to GitHub Settings → Secrets → Actions:
- `DATABASE_URL_RO` — the analyst_ro Session Pooler URL
- `ANTHROPIC_API_KEY` — current rotated key

### Baseline eval metrics (2026-06-16, Haiku 4.5, local)
7/7 pass · 3/3 judge=1 · $0.0170/suite · 21.2s · 1 soft warning (loop_mom cycles=0,
not a failure — loop mechanic proven by 11 unit tests)

---

## Phase 2 — Day 6: documentation close + seed determinism fix (DONE)
Goal: README final, CASE_STUDY.md, reproducibility verified — "terminado-contratable".

### Done — Day 6
1. [x] **Seed determinism fix** (`db/seed.py`): replaced `datetime.now(timezone.utc)` with
       `NOW_ANCHOR = datetime(2026, 6, 16, 0, 0, 0, tzinfo=timezone.utc)`. Any clone that runs
       `db/seed.py` with `SEED=42` now produces identical per-month counts. Canonical: 852 orders
       in May 2026 (confirmed via direct DB query + live Railway endpoint). Eval case updated to 852.
2. [x] **Reproducibility walkthrough verified** (clean clone at `/tmp/analyst-clone`):
       - `uv sync --frozen`: 61 packages in 3.86 s ✓
       - `db/apply_schema.py`: Applied schema.sql successfully ✓
       - `db/seed.py`: 200/50/5000/15164 rows with fixed anchor ✓
       - CLI agent: "852 orders in May 2026" — year guard in SQL ✓
       - Live Railway endpoint: "In May 2026, 852 orders were placed." ✓
3. [x] **README.md**: added Eval suite row (7/7 · 3/3 judge=1 · $0.017/run · 21 s) + Unit tests
       row (11 deterministic · 2.35 s). Removed Loom placeholder. Activated CASE_STUDY.md link.
4. [x] **CASE_STUDY.md** (new, 7 sections): problem → what I built → architecture → results (4 stories:
       loop recovery with real error trace, co-location 15×, security 3 layers, eval baseline) →
       decisions & trade-offs → v2 scope → honest scope note. All numbers real and sourced.
5. [x] **DECISIONS.md**: Day 6 section added (seed determinism fix, reproducibility evidence,
       canonical count = 852). Updated eval example from 856 → 852.
6. [x] Committed + pushed.

### Spec §8 status (ALL criteria met after Day 6)
- [x] Pregunta real → respuesta correcta end-to-end (Day 2)
- [x] Loop recovers from at least one real SQL error (Day 3)
- [x] Rejects destructive + out-of-schema (Day 3)
- [x] No inventa números (Day 3)
- [x] Suite de evals corrida: 7/7, baseline documentado, costo medido (Day 5)
- [x] Deployed in cloud, answers with laptop off (Day 4)
- [x] README reproducible — clone → run verified end-to-end in clean clone (Day 6) ← NEW

### Project status: TERMINADO-CONTRATABLE
All spec §8 acceptance criteria met. Evidence set complete.
