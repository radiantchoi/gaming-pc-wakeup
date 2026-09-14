# Implementation Plan — Gaming PC Wake-on-LAN Server (gaming-pc-wakeup)

Source of truth: `SPEC.md`. This plan is for fresh Pi workers with ~24K context.
Each task is self-contained: read `SPEC.md` + this file, do one task, verify its acceptance criteria, update `.agent/state.json`.

## Context for workers
- Toolchain: `uv` 0.12.x on PATH. Project targets `requires-python >= 3.11`; `.python-version` is `3.13` (matches the Pi's OS Python).
- Target device: Raspberry Pi 1 Model B, 32-bit Raspberry Pi OS Lite (trixie). Some tasks (T5, T11) run **on the Pi** and need a human; they cannot be done by a worker on the dev machine.
- Layout (decided, do not redesign):
  - `app/__init__.py` — empty.
  - `app/config.py` — reads env vars into a `Settings` dataclass; `load_settings()` raises `ValueError` with a clear message on missing/invalid `WOL_MAC` or missing `WOL_HOST`.
  - `app/wol.py` — pure functions `parse_mac(s) -> bytes`, `build_magic_packet(mac) -> bytes`, `send_magic_packet(mac, broadcast, port) -> None` (stdlib `socket` only).
  - `app/main.py` — `app = FastAPI()`; routes `GET /health`, `POST /wake`, `GET /status`. Settings are loaded at import time (module-level `settings = load_settings()`), so a bad env fails at startup.
  - `tests/__init__.py` — empty (makes `app` importable from `uv run pytest` without pytest config).
  - `tests/test_health.py`, `tests/test_wol.py`, `tests/test_config.py`, `tests/test_wake.py`, `tests/test_status.py`.
  - `deploy/gaming-pc-wakeup.service`, `README.md`.
- Env vars and endpoint contracts are defined in `SPEC.md` (Configuration, Endpoints). Do not invent others.
- Minimalism rule: no extra routes, no DI, no pydantic settings, no logging config, no CLI. Dependencies stay exactly: fastapi, uvicorn, pydantic-core (listed only so its piwheels source applies); dev: pytest, httpx, ruff.
- Tests never touch the network: monkeypatch `app.main.send_magic_packet` and the TCP connect helper. Tests set env vars with `monkeypatch.setenv` and import/reload `app.main` after setting them (use `importlib.reload`).
- Every code task ends with `uv run ruff check .` and `uv run pytest -q` passing.

## Tasks (ordered; do not skip ahead)

### T1 — Initialize uv project (DONE)
- `uv init`, project named `gaming-pc-wakeup`. Verified in `.agent/verification/T1.md`.

### T2 — Add dependencies (DONE)
- `uv add fastapi uvicorn`; `uv add --dev pytest httpx ruff`. Verified in `.agent/verification/T2.md`.

### T3 — Align toolchain with the Pi (DONE)
- Action:
  - `.python-version` → `3.13`.
  - `pyproject.toml`: `requires-python = ">=3.11"`; add `[[tool.uv.index]]` named `piwheels` (`https://www.piwheels.org/simple`, `explicit = true`) and `[tool.uv.sources]` pinning `pydantic-core` to that index with marker `platform_machine == 'armv6l' or platform_machine == 'armv7l'`. Add `pydantic-core` to `dependencies` (uv applies sources to direct dependencies only; verified by experiment).
  - `uv lock` then `uv sync`.
- Acceptance:
  - `uv sync` exits 0 on the dev machine (PyPI wheels used there).
  - `uv.lock` contains a `pydantic-core` entry sourced from `https://www.piwheels.org/simple` whose wheels include `linux_armv6l` files.
  - `uv run python -c "import fastapi, uvicorn"` exits 0.
  - Dependencies: fastapi, uvicorn, pydantic-core; dev: httpx, pytest, ruff.
- Result: see `.agent/findings/T3.md`.

### T4 — Implement `GET /health` with test
- Action: create `app/__init__.py`, `app/main.py` with `app = FastAPI()` and `@app.get("/health")` returning `{"status": "ok"}`; `tests/__init__.py`; `tests/test_health.py` using `TestClient(app)`.
  - Do **not** add config loading yet; `/health` must not depend on env vars.
- Acceptance:
  - `uv run uvicorn app.main:app --port 8765` starts; `curl -s localhost:8765/health` → 200 `{"status":"ok"}`; `/nope` → 404; stop the server.
  - `uv run pytest -q` → 1 passed. `uv run ruff check .` exits 0.

### T5 — On-device gate (HUMAN, on the Pi 1 Model B)
- Action (performed by the user on the Pi, results recorded in `.agent/findings/T5.md`):
  1. Flash Raspberry Pi OS Lite (32-bit, trixie); boot; `python3 --version` (expect 3.13.x); `uname -m` (expect `armv6l`); `free -m` (record RAM).
  2. Install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`; `uv --version`.
  3. Clone repo; `UV_PYTHON_DOWNLOADS=never uv sync` — record wall time and whether `pydantic-core` came from piwheels as a wheel (no Rust build).
  4. `UV_PYTHON_DOWNLOADS=never uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`; record seconds to "Application startup complete"; `curl localhost:8000/health` → 200.
- Acceptance: steps 3 and 4 succeed. Record RAM, sync time, startup time, RSS (`ps -o rss= -C python3`).
- Contingency: if step 3 cannot install `pydantic-core` as a wheel, set `status: "blocked"` with reason `pydantic-core unavailable on armv6l` and stop. The next plan revision replaces FastAPI/uvicorn/httpx with stdlib `http.server` per `SPEC.md` "On-device gate and contingency"; endpoint contracts and later tasks stay the same.

### T6 — WoL module
- Action: create `app/wol.py`:
  - `parse_mac(s)`: accept `AA:BB:CC:DD:EE:FF`, `AA-BB-CC-DD-EE-FF`, `AABBCCDDEEFF` (any case); return 6 bytes; raise `ValueError` otherwise.
  - `format_mac(mac: bytes) -> str`: upper-case, colon-separated.
  - `build_magic_packet(mac)`: `b"\xff" * 6 + mac * 16` (102 bytes).
  - `send_magic_packet(mac, broadcast, port)`: UDP socket with `SO_BROADCAST`, one `sendto`, close (use `with`).
  - `tests/test_wol.py`: three formats parse to the same bytes; invalid strings (`""`, 5 octets, non-hex, 13 hex chars) raise `ValueError`; packet is 102 bytes, starts with 6×`0xff`, tail is MAC×16; `format_mac` round-trips.
- Acceptance: `uv run pytest -q` all pass (health + wol); `uv run ruff check .` exits 0. No network access in tests.

### T7 — Configuration
- Action: create `app/config.py` with a frozen `dataclass Settings(mac: bytes, broadcast: str, port: int, host: str, status_port: int, status_timeout: float, token: str | None)` and `load_settings(env=os.environ) -> Settings` applying the defaults from `SPEC.md`. Missing `WOL_MAC`/`WOL_HOST` or invalid MAC → `ValueError` whose message names the variable.
  - `tests/test_config.py`: defaults applied; each required var missing raises with the var name in the message; invalid MAC raises; custom values parsed (ints/float).
- Acceptance: `uv run pytest -q` all pass; `uv run ruff check .` exits 0.

### T8 — `POST /wake`
- Action: in `app/main.py`, add `settings = load_settings()` at module level and `@app.post("/wake")`:
  - If `settings.token` is set and header `X-Token` != token → `HTTPException(401, "invalid token")`.
  - Call `send_magic_packet(settings.mac, settings.broadcast, settings.port)`; on `OSError` → `HTTPException(502, str(exc))`.
  - Return `{"status": "sent", "mac": format_mac(settings.mac), "broadcast": ..., "port": ...}`.
  - `tests/test_wake.py`: set env via `monkeypatch.setenv`, `importlib.reload(app.main)`, monkeypatch `app.main.send_magic_packet` with a recorder; assert it is called once with the configured MAC/broadcast/port and the body matches; 401 when token set and header wrong/missing; 200 when token set and header correct; 502 when the sender raises `OSError`; `GET /wake` → 405.
  - Update `tests/test_health.py` so `/health` still passes with env set (it must not require env, but `app.main` import now does — set `WOL_MAC`/`WOL_HOST` in that test too).
- Acceptance: `uv run pytest -q` all pass; `uv run ruff check .` exits 0; `WOL_MAC=aa:bb:cc:dd:ee:ff WOL_HOST=192.0.2.10 uv run uvicorn app.main:app --port 8765` starts and `curl -X POST localhost:8765/wake` returns the documented body (a real broadcast is sent; that is fine); running uvicorn **without** `WOL_MAC` exits non-zero with a message naming `WOL_MAC`.

### T9 — `GET /status`
- Action: add `is_port_open(host, port, timeout) -> bool` to `app/wol.py` (`socket.create_connection` in `with`; `OSError` → `False`). Add `@app.get("/status")` returning `{"online": bool, "host": settings.host, "port": settings.status_port}`.
  - `tests/test_status.py`: monkeypatch `app.main.is_port_open` → True/False and assert bodies; one direct test of `is_port_open` against a bound-but-closed local port returning `False` (localhost only, allowed).
- Acceptance: `uv run pytest -q` all pass; `uv run ruff check .` exits 0.

### T10 — Deployment artifacts
- Action:
  - `deploy/gaming-pc-wakeup.service`: `[Service]` with `WorkingDirectory=/home/pi/gaming-pc-wakeup`, `EnvironmentFile=/etc/gaming-pc-wakeup.env`, `Environment=UV_PYTHON_DOWNLOADS=never`, `ExecStart=/home/pi/.local/bin/uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`, `Restart=on-failure`, `User=pi`; `[Install] WantedBy=multi-user.target`.
  - `README.md`: sections exactly as listed in `SPEC.md` "Deployment artifacts" (flash OS, install uv, clone + sync, env file + enable service, Tailscale install and URL, PC prerequisites, curl examples for the three endpoints). Keep it short; no marketing text.
- Acceptance: files exist; `systemd-analyze verify deploy/gaming-pc-wakeup.service` is not available on macOS, so instead check the unit has the keys above; README mentions every env var from `SPEC.md`.

### T11 — Final verification (local + on-device, HUMAN for the on-device part)
- Local checklist (worker): `uv sync` 0; `uv run ruff check .` 0; `uv run pytest -q` all pass; server starts with env and returns documented responses for the three endpoints; 404 for other paths; refuses to start without `WOL_MAC`.
- On-device (user, record in `.agent/findings/T11.md`): pull on the Pi, `uv sync`, install env file and service, `systemctl enable --now gaming-pc-wakeup`, reboot, confirm service active; from a Tailscale client `POST /wake` turns the PC on and `GET /status` flips to `online: true`.
- Acceptance: all local checks pass and the on-device result is recorded. Then set `status: "done"`.

## Orchestration notes
- After each task: update `.agent/state.json` (`completed_tasks`, `current_task`, `iteration`, `status`), and write `.agent/findings/<task>.md`.
- On failure: record task in `failed_tasks` with a one-line reason, set `status: "blocked"`, do not retry more than twice before blocking.
- T5 and T11 need the user at the Pi; set `current_task_status: "waiting_for_human"` when reaching them.
- When T11 passes: set `status: "done"` in `.agent/state.json`.
