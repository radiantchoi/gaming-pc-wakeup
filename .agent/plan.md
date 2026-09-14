# Implementation Plan — FastAPI Experiment (gaming-pc-wakeup)

Source of truth: `SPEC.md`. This plan is for fresh Pi workers with ~24K context.
Each task is self-contained: read `SPEC.md` + this file, do one task, verify its acceptance criteria, update `.agent/state.json`.

## Context for workers
- Toolchain: `uv` 0.12.1 (available on PATH), Python 3.14.
- Layout (decided, do not redesign):
  - `app/main.py` — single FastAPI app module, `app = FastAPI()`, one route `GET /health`.
  - `tests/test_health.py` — one test using `fastapi.testclient.TestClient`.
- Minimalism rule: no extra routes, no config, no DI, no abstractions, no README beyond `uv init` default.
- Health response contract: HTTP 200, JSON body `{"status": "ok"}`.

## Tasks (ordered; do not skip ahead)

### T1 — Initialize uv project
- Action: run `uv init --name gaming-pc-wakeup --python 3.14` in the repo root. Remove the generated `main.py` (our app lives in `app/main.py` later). Keep `pyproject.toml`, `.python-version`, `README.md`.
- Acceptance:
  - `pyproject.toml` exists with `name = "gaming-pc-wakeup"`.
  - `.python-version` exists.
  - `uv sync` exits 0.
  - No other source files exist yet.

### T2 — Add dependencies
- Action: `uv add fastapi uvicorn` and `uv add --dev pytest httpx ruff`.
  - `httpx` is required by `TestClient`; `ruff` is the PEP 8 checker. Nothing else.
- Acceptance:
  - `uv sync` exits 0 and `uv.lock` is created.
  - `pyproject.toml` lists exactly: dependencies = fastapi, uvicorn; dev group = pytest, httpx, ruff.
  - `uv run python -c "import fastapi, uvicorn"` exits 0.

### T3 — Implement `GET /health`
- Action: create `app/__init__.py` (empty) and `app/main.py` containing only: `app = FastAPI()` and a `@app.get("/health")` route returning `{"status": "ok"}`. PEP 8 compliant (ruff clean).
- Acceptance:
  - `uv run uvicorn app.main:app --port 8765` starts without error.
  - `curl -s localhost:8765/health` returns HTTP 200 with body `{"status":"ok"}`.
  - `curl -s -o /dev/null -w '%{http_code}' localhost:8765/nope` returns 404 (no extra routes).
  - `uv run ruff check app` exits 0.
  - Server process is stopped afterwards.

### T4 — Add test for `GET /health`
- Action: create `tests/test_health.py` with one test: build `TestClient(app)` from `app.main`, `GET /health`, assert status 200 and JSON body `{"status": "ok"}`.
- Acceptance:
  - `uv run pytest -q` exits 0 with exactly 1 test passed.
  - `uv run ruff check tests` exits 0.
  - No test infrastructure beyond the single file (no conftest, no fixtures, no pytest config needed).

### T5 — Final verification against SPEC completion criteria
- Action: run the full checklist, fix nothing unless a criterion fails (if it fails, report failure instead of expanding scope):
  1. `uv sync` exits 0.
  2. `uv run uvicorn app.main:app --port 8765` starts; `curl -s localhost:8765/health` → 200 `{"status":"ok"}`; stop server.
  3. `uv run pytest -q` → 1 passed.
  4. `uv run ruff check .` exits 0.
- Acceptance: all four commands succeed; report results in the task output.

## Orchestration notes
- After each task: update `.agent/state.json` (`completed_tasks`, `current_task`, `iteration`, `status`).
- On failure: record task in `failed_tasks` with a one-line reason, set `status: "blocked"`, do not retry more than twice before blocking.
- When T5 passes: set `status: "done"` in `.agent/state.json`.
