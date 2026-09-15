# Implementation Plan — Gaming PC Wake-on-LAN Server (gaming-pc-wakeup)

Source of truth: `SPEC.md`. This plan is for fresh Pi workers with ~24K context.
Each task is self-contained: read `SPEC.md` + this file, do one task, verify its acceptance criteria, update `.agent/state.json`.

## Context for workers
- Toolchain: `uv` 0.12.x on PATH. `requires-python >= 3.11`; no `.python-version` (each machine uses its own interpreter). `pyproject.toml` and `uv.lock` are host-neutral; every host-specific workaround lives only under `deploy/<host>/`.
- Hosts (both supported, either is enough): Raspberry Pi 1 Model B (32-bit Pi OS Lite trixie, Python 3.13, needs piwheels for `pydantic-core`) and Galaxy Note 8 with Termux (Android 9, Python 3.14, Rust available so `pydantic-core` builds). Tasks T5 and T11 run **on a host** and need a human; they cannot be done by a worker on the dev machine.
- Layout (decided, do not redesign):
  - `app/__init__.py` — empty.
  - `app/config.py` — reads env vars into a `Settings` dataclass; `load_settings()` raises `ValueError` with a clear message on missing/invalid `WOL_MAC` or missing `WOL_HOST`.
  - `app/wol.py` — pure functions `parse_mac(s) -> bytes`, `build_magic_packet(mac) -> bytes`, `send_magic_packet(mac, broadcast, port) -> None` (stdlib `socket` only).
  - `app/main.py` — `app = FastAPI()`; routes `GET /health`, `POST /wake`, `GET /status`. Settings are loaded at import time (module-level `settings = load_settings()`), so a bad env fails at startup.
  - `tests/__init__.py` — empty (makes `app` importable from `uv run pytest` without pytest config).
  - `tests/test_health.py`, `tests/test_wol.py`, `tests/test_config.py`, `tests/test_wake.py`, `tests/test_status.py`.
  - `deploy/common/gaming-pc-wakeup.env.example`; `deploy/pi/install.sh`, `deploy/pi/gaming-pc-wakeup.service`; `deploy/termux/install.sh`, `deploy/termux/boot.sh`; `README.md`.
- Env vars and endpoint contracts are defined in `SPEC.md` (Configuration, Endpoints). Do not invent others.
- Minimalism rule: no extra routes, no DI, no pydantic settings, no logging config, no CLI. Dependencies stay exactly: fastapi, uvicorn; dev: pytest, httpx, ruff. Nothing host-specific in `pyproject.toml`.
- Tests never touch the network: monkeypatch `app.main.send_magic_packet` and the TCP connect helper. Tests set env vars with `monkeypatch.setenv` and import/reload `app.main` after setting them (use `importlib.reload`).
- Every code task ends with `uv run ruff check .` and `uv run pytest -q` passing.

## Tasks (ordered; do not skip ahead)

### T1 — Initialize uv project (DONE)
- `uv init`, project named `gaming-pc-wakeup`. Verified in `.agent/verification/T1.md`.

### T2 — Add dependencies (DONE)
- `uv add fastapi uvicorn`; `uv add --dev pytest httpx ruff`. Verified in `.agent/verification/T2.md`.

### T3 — Align toolchain with the Pi (DONE, superseded by T3b)
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

### T3b — Make the toolchain host-neutral (DONE)
- Why: a second host (Note 8 + Termux, aarch64, Android) was added. The piwheels index, the `pydantic-core` source pin, the `pydantic-core` direct dependency, and `.python-version = 3.13` were all Pi-only and would get in the way on Termux (its Python is 3.14 and uv cannot download 3.13 there).
- Action: remove `[[tool.uv.index]]`, `[tool.uv.sources]`, and `pydantic-core` from `pyproject.toml`; delete `.python-version`; `uv lock`; `uv sync`. The piwheels workaround moves to `deploy/pi/install.sh` (T10).
- Acceptance: `pyproject.toml` has exactly fastapi, uvicorn (dev: httpx, pytest, ruff) and no `tool.uv` table; no `.python-version`; `uv.lock` has no piwheels entries and no `resolution-markers` fork; `uv sync`, `uv run ruff check .`, `uv run pytest -q` all pass.
- Result: see `.agent/findings/T3b.md`.

### T4 — Implement `GET /health` with test
- Action: create `app/__init__.py`, `app/main.py` with `app = FastAPI()` and `@app.get("/health")` returning `{"status": "ok"}`; `tests/__init__.py`; `tests/test_health.py` using `TestClient(app)`.
  - Do **not** add config loading yet; `/health` must not depend on env vars.
- Acceptance:
  - `uv run uvicorn app.main:app --port 8765` starts; `curl -s localhost:8765/health` → 200 `{"status":"ok"}`; `/nope` → 404; stop the server.
  - `uv run pytest -q` → 1 passed. `uv run ruff check .` exits 0.

### T5 — Host gates (HUMAN, on each host; does not block T6–T10)
- T5-pi (Raspberry Pi 1 Model B), results in `.agent/findings/T5-pi.md`:
  1. Flash Raspberry Pi OS Lite (32-bit, trixie); boot; `python3 --version` (expect 3.13.x); `uname -m` (expect `armv6l`); `free -m` (record RAM).
  2. Install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`; `uv --version`.
  3. Clone repo; run `deploy/pi/install.sh` (needs T10; until then run its commands by hand: `uv venv --python python3`, `uv export --frozen --no-dev --no-hashes -o /tmp/req.txt`, `uv pip install --index https://www.piwheels.org/simple --index-strategy unsafe-best-match -r /tmp/req.txt`). Record wall time and whether `pydantic-core` installed as a `linux_armv6l` wheel (no Rust build).
  4. `WOL_MAC=... WOL_HOST=... .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000`; record seconds to "Application startup complete"; `curl localhost:8000/health` → 200.
  - Pass: steps 3 and 4 succeed. Record RAM, install time, startup time, RSS.
  - Fail: record the reason; the Pi 1 is dropped as a host and `deploy/pi/` is removed in T10. No other change.
- T5-termux (Galaxy Note 8), results in `.agent/findings/T5-termux.md`:
  1. Termux (F-Droid/GitHub build) with `python`, `uv`, `rust` installed; `python --version`; `uname -m` (expect `aarch64`).
  2. Clone repo; `UV_PYTHON_DOWNLOADS=never uv sync --no-dev`; record wall time (first run builds `pydantic-core`).
  3. `WOL_MAC=... WOL_HOST=... .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000`; `curl localhost:8000/health` → 200.
  4. Leave it running with the screen off overnight (`termux-wake-lock` on, battery optimisation off); next morning `curl` again.
  - Pass: steps 2–4 succeed. Record sync time and whether the overnight check passed.
  - Fail on step 4 only: not a code problem; record which Android setting was missing and retry once.
- At least one of T5-pi / T5-termux must pass before T11.

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
- Action (contents specified in `SPEC.md` "Deployment artifacts"):
  - `deploy/common/gaming-pc-wakeup.env.example`: all seven `WOL_*` variables, `KEY=value`, defaults filled in, placeholders for `WOL_MAC` and `WOL_HOST`, no quotes, no `export`.
  - `deploy/pi/install.sh`: `#!/bin/sh`, `set -eu`, `cd` to the repo root (`$(dirname "$0")/../..`), `export UV_PYTHON_DOWNLOADS=never`, `uv venv --python python3` (skip if `.venv` exists), `uv export --frozen --no-dev --no-hashes -o "$tmp"`, `uv pip install --index https://www.piwheels.org/simple --index-strategy unsafe-best-match -r "$tmp"`.
  - `deploy/pi/gaming-pc-wakeup.service`: `[Unit] Description`, `After=network-online.target`; `[Service] User=pi`, `WorkingDirectory=/home/pi/gaming-pc-wakeup`, `EnvironmentFile=/etc/gaming-pc-wakeup.env`, `ExecStart=/home/pi/gaming-pc-wakeup/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000`, `Restart=on-failure`; `[Install] WantedBy=multi-user.target`.
  - `deploy/termux/install.sh`: `#!/data/data/com.termux/files/usr/bin/sh`, `set -eu`, `pkg install -y python uv rust`, `cd` to repo root, `UV_PYTHON_DOWNLOADS=never uv sync --no-dev`.
  - `deploy/termux/boot.sh`: same shebang, `termux-wake-lock`, `cd` to repo root (`$HOME/gaming-pc-wakeup`), `set -a; . "$HOME/gaming-pc-wakeup.env"; set +a`, `exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000`.
  - `README.md`: sections in the order given in `SPEC.md`. Keep it short; no marketing text.
  - If T5-pi has failed by now, omit `deploy/pi/` and the Pi section of the README.
- Acceptance: files exist and are executable where they are scripts (`chmod +x`); `sh -n` passes on each script; the unit has the keys above; README mentions every env var from `SPEC.md`; `deploy/pi/install.sh` runs to completion on the dev machine (piwheels index is harmless there; PyPI wheels win) and the resulting `.venv` passes `uv run --no-sync pytest -q`.

### T11 — Final verification (local + on-device, HUMAN for the on-device part)
- Local checklist (worker): `uv sync` 0; `uv run ruff check .` 0; `uv run pytest -q` all pass; server starts with env and returns documented responses for the three endpoints; 404 for other paths; refuses to start without `WOL_MAC`.
- On-device (user, record in `.agent/findings/T11.md`), on every host that passed T5:
  - Pi: pull, `deploy/pi/install.sh`, install env file and service, `systemctl enable --now gaming-pc-wakeup`, reboot, confirm active.
  - Termux: pull, `deploy/termux/install.sh`, copy `boot.sh` to `~/.termux/boot/`, reboot the phone, confirm the server answers.
  - From a Tailscale client: `POST /wake` turns the PC on and `GET /status` flips to `online: true`.
- Acceptance: all local checks pass and at least one host's on-device result is recorded as passing; untested hosts are marked as such in the README. Then set `status: "done"`.

## Orchestration notes
- After each task: update `.agent/state.json` (`completed_tasks`, `current_task`, `iteration`, `status`), and write `.agent/findings/<task>.md`.
- On failure: record task in `failed_tasks` with a one-line reason, set `status: "blocked"`, do not retry more than twice before blocking.
- T5 and T11 need the user at a host; set `current_task_status: "waiting_for_human"` when reaching them. T5 does not block T6–T10.
- When T11 passes: set `status: "done"` in `.agent/state.json`.
