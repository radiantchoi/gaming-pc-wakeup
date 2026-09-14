# Gaming PC Wake-on-LAN Server

## Goal
Build a minimal FastAPI server that runs on a Raspberry Pi and wakes a single
gaming PC on the same local network via Wake-on-LAN (WoL), and reports whether
that PC is currently reachable.

## Deployment context
- Target hardware: Raspberry Pi 1 Model B (BCM2835, ARMv6, single core
  700 MHz, 256 MB or 512 MB RAM depending on revision, 100 Mbps Ethernet).
  This is a 32-bit-only board.
- OS: fresh install of Raspberry Pi OS Lite (32-bit, Debian 13 "trixie"),
  which ships Python 3.13. No desktop.
- Runs directly on the host (no Docker; container bridges block UDP
  broadcast).
- The Pi is connected by Ethernet to the same L2 broadcast domain as the
  gaming PC (same subnet and VLAN). The PC is connected by Ethernet.
- Python: the OS-provided interpreter is used. `uv` must not try to download
  a managed Python (there are no ARMv6 builds); set
  `UV_PYTHON_DOWNLOADS=never` on the Pi.
- Package index: PyPI has no ARMv6 wheels for `pydantic-core`. The project
  configures https://www.piwheels.org/simple as an additional index in
  `pyproject.toml` so that `uv sync` on the Pi installs prebuilt
  `linux_armv6l` wheels instead of compiling.
- The server runs as a `systemd` service and starts on boot.

## Remote access
- Remote use (outside the LAN) goes through Tailscale installed on the Pi and
  on the client device. The server binds to `0.0.0.0:8000` and is reached at
  its Tailscale address; nothing is exposed to the public internet.
- Tailscale is not part of this codebase. The README documents installing it
  from the Raspberry Pi OS apt repository and the resulting URL pattern.
- `WOL_TOKEN` remains an optional second layer; it is not required when
  access is limited to the tailnet.

## Requirements

### Toolchain and style
- Use `uv` for project and dependency management.
- Use Python and FastAPI. `requires-python = ">=3.11"`; `.python-version`
  is `3.13` to match the Pi. Development on other machines may use any
  3.11+ interpreter.
- Follow PEP 8; `ruff check .` must pass.
- Keep the implementation minimal and easy to verify. Avoid unnecessary
  dependencies, abstractions, and features.
- WoL is implemented with the standard library `socket` module only.
  No third-party WoL package.

### Configuration
All configuration comes from environment variables. No config files, no CLI
flags.

| Variable             | Required | Default             | Meaning |
|----------------------|----------|---------------------|---------|
| `WOL_MAC`            | yes      |                     | MAC address of the gaming PC's Ethernet NIC. Accept `AA:BB:CC:DD:EE:FF`, `AA-BB-CC-DD-EE-FF`, and `AABBCCDDEEFF`, case-insensitive. |
| `WOL_BROADCAST`      | no       | `255.255.255.255`   | Broadcast address the magic packet is sent to. |
| `WOL_PORT`           | no       | `9`                 | UDP port the magic packet is sent to. |
| `WOL_HOST`           | yes      |                     | IP address or hostname of the gaming PC, used by `GET /status`. |
| `WOL_STATUS_PORT`    | no       | `3389`              | TCP port on the PC that is open when it is up (RDP by default). |
| `WOL_STATUS_TIMEOUT` | no       | `1.0`               | Seconds to wait for the TCP connect in `GET /status`. |
| `WOL_TOKEN`          | no       | unset               | If set, `POST /wake` requires header `X-Token: <value>`; otherwise no auth. |

- The server must fail at startup with a clear error if `WOL_MAC` is missing
  or not a valid MAC, or if `WOL_HOST` is missing.

### Endpoints
Expose exactly these three endpoints. Any other path returns 404.

- `GET /health`
  - Always `200` with body `{"status": "ok"}`.
  - No dependency on configuration or network.
- `POST /wake`
  - Builds a WoL magic packet (6 bytes of `0xFF` followed by the MAC
    repeated 16 times, 102 bytes total) and sends it once as a UDP broadcast
    to `WOL_BROADCAST:WOL_PORT`.
  - `200` with body `{"status": "sent", "mac": "<normalized MAC>",
    "broadcast": "<addr>", "port": <int>}`. Normalized MAC is upper-case,
    colon-separated.
  - `401` with body `{"detail": "invalid token"}` if `WOL_TOKEN` is set and
    the `X-Token` header is missing or wrong.
  - `502` with body `{"detail": "<message>"}` if the socket send fails.
  - `GET /wake` is not allowed (405 by default from FastAPI).
- `GET /status`
  - Attempts a TCP connect to `WOL_HOST:WOL_STATUS_PORT` with
    `WOL_STATUS_TIMEOUT`.
  - `200` with body `{"online": true|false, "host": "<WOL_HOST>",
    "port": <int>}`. Connection refused or timeout means `online: false`;
    it is not an error.

### Code layout
- `app/__init__.py` (empty)
- `app/config.py` — reads and validates the environment variables above.
- `app/wol.py` — pure functions: `parse_mac(str) -> bytes`,
  `build_magic_packet(mac: bytes) -> bytes`, and
  `send_magic_packet(mac: bytes, broadcast: str, port: int) -> None`.
- `app/main.py` — the FastAPI app and the three routes only.
- `tests/` — pytest tests (see below).
- `deploy/gaming-pc-wakeup.service` — systemd unit template.
- `README.md` — setup for the Pi and prerequisites for the PC.

### Tests
- Use `pytest` and `fastapi.testclient.TestClient`.
- Tests must not send real network traffic. Patch `send_magic_packet` and the
  TCP connect used by `GET /status`.
- Cover at least:
  - `GET /health` returns `200` `{"status": "ok"}`.
  - `parse_mac` accepts the three formats and rejects invalid input.
  - `build_magic_packet` returns 102 bytes with the correct prefix and
    16 repetitions of the MAC.
  - `POST /wake` calls the sender with the configured MAC, broadcast, and
    port and returns the documented body.
  - `POST /wake` returns `401` when `WOL_TOKEN` is set and the header is
    wrong.
  - `GET /status` returns `online: true` on successful connect and
    `online: false` on refusal or timeout.
- Configuration is supplied to tests via environment variables (for example
  `monkeypatch.setenv`); no test-only config paths in application code.

### Deployment artifacts
- `deploy/gaming-pc-wakeup.service`: runs
  `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000` from the project
  directory, reads variables from an `EnvironmentFile`, sets
  `UV_PYTHON_DOWNLOADS=never`, restarts on failure, and is
  `WantedBy=multi-user.target`.
- `README.md` documents:
  - Flashing Raspberry Pi OS Lite (32-bit, trixie).
  - Installing `uv` on the Pi (ARMv6 build), cloning the repo,
    `UV_PYTHON_DOWNLOADS=never uv sync`.
  - Creating the environment file and enabling the service.
  - Installing Tailscale on the Pi and reaching the server over the tailnet.
  - PC prerequisites: WoL enabled in BIOS/UEFI, NIC driver set to allow
    waking the computer, Windows Fast Startup disabled, Ethernet connection.
  - Example `curl` commands for the three endpoints.

## On-device gate and contingency
- Before the endpoints are implemented, `uv sync` and a `GET /health`
  smoke test must succeed on the Pi 1 itself (dependencies resolve from
  piwheels, server starts, startup time is recorded).
- If `uv sync` cannot install `pydantic-core` on the Pi, the contingency is
  to drop FastAPI, uvicorn, and httpx and implement the same three endpoints
  with the standard library `http.server`. The endpoint contracts,
  configuration, tests, and deployment artifacts in this document stay the
  same; only the "Use FastAPI" and `TestClient` requirements change.

## Non-goals
- No web UI.
- No multiple targets or per-request MAC addresses.
- No scheduling, shutdown, sleep, or remote-desktop features.
- No Docker image.
- No persistent storage.

## Completion Criteria
- `uv sync` exits 0.
- `uv run ruff check .` exits 0.
- `uv run pytest -q` exits 0 with all tests passing.
- With `WOL_MAC` and `WOL_HOST` set, `uv run uvicorn app.main:app` starts;
  `GET /health`, `POST /wake`, and `GET /status` return the documented
  responses; any other path returns 404.
- Without `WOL_MAC`, the server refuses to start with a clear error.
- `deploy/gaming-pc-wakeup.service` and `README.md` exist and match the
  behaviour above.
- On the Pi 1 Model B: `uv sync` completes using piwheels wheels, the
  service starts on boot, and `POST /wake` from a Tailscale-connected client
  turns the gaming PC on.
