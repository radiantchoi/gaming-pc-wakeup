# Gaming PC Wake-on-LAN Server

## Goal
Build a minimal FastAPI server that runs on a small always-on host (a
Raspberry Pi 1 or an old Android phone under Termux) and wakes a single gaming
PC on the same local network via Wake-on-LAN (WoL), reports whether that PC
is currently reachable, and can put it to sleep over SSH.

## Deployment context
Common to all hosts:
- Runs directly on the host (no Docker; container bridges block UDP
  broadcast).
- The host is on the same L2 broadcast domain as the gaming PC (same subnet
  and VLAN). The PC is connected by Ethernet; the host may use Ethernet or
  Wi-Fi.
- Python: the host's own interpreter (3.11+). `uv` must not download a
  managed Python on either host (there is no ARMv6 build and no
  Android/bionic build): set `UV_PYTHON_DOWNLOADS=never` there.
- `pyproject.toml` and `uv.lock` are host-neutral. Every host-specific
  workaround lives under `deploy/<host>/` and nowhere else.
- The server starts on boot and restarts on failure, by whatever mechanism
  the host provides.

Two hosts are supported in parallel; either one is sufficient.

### Host A: Raspberry Pi 1 Model B
- BCM2835, ARMv6, single core 700 MHz, 256 MB or 512 MB RAM by revision,
  100 Mbps Ethernet. 32-bit only.
- OS: fresh Raspberry Pi OS Lite (32-bit, Debian 13 "trixie"), Python 3.13,
  no desktop.
- PyPI has no ARMv6 wheels for `pydantic-core`; piwheels does.
  `deploy/pi/install.sh` creates `.venv` with the system Python, exports
  pinned versions from `uv.lock` (`uv export`), and installs them with
  `uv pip install` using https://www.piwheels.org/simple as an additional
  index (`--index-strategy unsafe-best-match`). `pyproject.toml` does not
  mention piwheels.
- Runs as a `systemd` service (`deploy/pi/gaming-pc-wakeup.service`) that
  executes `.venv/bin/uvicorn` directly, so uv is not involved at runtime.

### Host B: Samsung Galaxy Note 8 with Termux
- aarch64, 6 GB RAM, Android 9, Wi-Fi. Termux from F-Droid or GitHub (not
  the Play Store build).
- Python from `pkg install python` (3.14 at the time of writing), `uv` from
  `pkg install uv`, `rust` from `pkg install rust` so that `pydantic-core`
  builds from source once (uv caches the built wheel).
- `deploy/termux/install.sh` runs `UV_PYTHON_DOWNLOADS=never uv sync`.
  `deploy/termux/boot.sh` (copied to `~/.termux/boot/`) acquires
  `termux-wake-lock` and starts `.venv/bin/uvicorn`; the Termux:Boot app
  provides start-on-boot.
- Android background limits are handled outside the code: Termux excluded
  from battery optimisation, Wi-Fi sleep disabled, phone kept on power. The
  README lists these steps.

## Remote access
- Remote use (outside the LAN) goes through Tailscale installed on the host
  and on the client device. The server binds to `0.0.0.0:8000` and is reached
  at its Tailscale address; nothing is exposed to the public internet.
- Tailscale is not part of this codebase. The README documents installing it
  on each host (apt repository on the Pi, the Android app on the phone) and
  the resulting URL pattern.
- `WOL_TOKEN` remains an optional second layer; it is not required when
  access is limited to the tailnet.

## Requirements

### Toolchain and style
- Use `uv` for project and dependency management.
- Use Python and FastAPI. `requires-python = ">=3.11"`. There is no
  `.python-version`; each machine uses its own interpreter that satisfies
  the range. Dependencies are exactly fastapi and uvicorn (dev: pytest,
  httpx, ruff).
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
| `WOL_TOKEN`          | no       | unset               | If set, `POST /wake` and `POST /sleep` require header `X-Token: <value>`; otherwise no auth. |
| `WOL_SSH_USER`       | no       | unset               | Windows user name for `POST /sleep`. Set together with `WOL_SSH_KEY`. |
| `WOL_SSH_KEY`        | no       | unset               | Path to the private key the host uses to SSH into the PC. Must exist. |
| `WOL_SSH_PORT`       | no       | `22`                | SSH port on the PC. |
| `WOL_SSH_TIMEOUT`    | no       | `10.0`              | Seconds allowed for the whole `ssh` invocation in `POST /sleep`. |

- The server must fail at startup with a clear error if `WOL_MAC` is missing
  or not a valid MAC, or if `WOL_HOST` is missing.
- It must also fail at startup if only one of `WOL_SSH_USER`/`WOL_SSH_KEY`
  is set, or if `WOL_SSH_KEY` points to a file that does not exist. With
  neither set, sleep is simply not configured.

### Endpoints
Expose exactly these four endpoints. Any other path returns 404.

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
- `POST /sleep`
  - Runs, via the host's `ssh` client:
    `ssh -i <WOL_SSH_KEY> -p <WOL_SSH_PORT> -o BatchMode=yes
    -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new
    <WOL_SSH_USER>@<WOL_HOST> schtasks /run /tn gaming-pc-sleep`
    with `WOL_SSH_TIMEOUT` as the overall timeout. The PC side is a
    scheduled task named `gaming-pc-sleep` that suspends the machine a
    moment later, so the SSH session closes cleanly before the PC sleeps
    (see `deploy/windows/`).
  - `200` with body `{"status": "sleeping", "host": "<WOL_HOST>"}` when
    `ssh` exits 0.
  - `401` with body `{"detail": "invalid token"}` under the same rule as
    `POST /wake`.
  - `503` with body `{"detail": "sleep is not configured: set WOL_SSH_USER
    and WOL_SSH_KEY"}` when sleep is not configured.
  - `502` with body `{"detail": "<message>"}` when `ssh` is missing, exits
    non-zero (message is its stderr, or the exit code if stderr is empty),
    or times out.
  - Whether the PC actually slept is observed with `GET /status`.

### Code layout
- `app/__init__.py` (empty)
- `app/config.py` — reads and validates the environment variables above.
- `app/wol.py` — pure functions: `parse_mac(str) -> bytes`,
  `build_magic_packet(mac: bytes) -> bytes`, and
  `send_magic_packet(mac: bytes, broadcast: str, port: int) -> None`.
- `app/sleep.py` — `request_sleep(host, user, key, port, timeout) -> None`;
  builds the `ssh` command above, runs it with `subprocess.run`, raises
  `RuntimeError` with a message on any failure.
- `app/main.py` — the FastAPI app and the four routes only.
- `tests/` — pytest tests (see below).
- `deploy/common/gaming-pc-wakeup.env.example` — environment file template.
- `deploy/pi/` — everything specific to the Raspberry Pi 1: `install.sh`,
  `gaming-pc-wakeup.service`.
- `deploy/termux/` — everything specific to the Note 8: `install.sh`,
  `boot.sh`.
- `deploy/windows/sleep.ps1` — the script the PC's `gaming-pc-sleep`
  scheduled task runs.
- `README.md` — setup per host and prerequisites for the PC.

### Tests
- Use `pytest` and `fastapi.testclient.TestClient`.
- Tests must not send real network traffic. Patch `send_magic_packet`, the
  TCP connect used by `GET /status`, and `subprocess.run` under
  `request_sleep`. Never invoke a real `ssh`.
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
  - `request_sleep` builds exactly the documented `ssh` argv and maps a
    non-zero exit, a missing `ssh` binary, and a timeout to `RuntimeError`.
  - `POST /sleep` returns `503` when unconfigured, `401` on a bad token,
    `200` with the documented body on success, and `502` when
    `request_sleep` raises.
  - Startup fails when only one of `WOL_SSH_USER`/`WOL_SSH_KEY` is set or
    the key file is missing.
- Configuration is supplied to tests via environment variables (for example
  `monkeypatch.setenv`); no test-only config paths in application code.

### Deployment artifacts
- `deploy/common/gaming-pc-wakeup.env.example`: every `WOL_*` variable with
  its default or a placeholder, one per line, `KEY=value` form (readable by
  systemd `EnvironmentFile` and by `set -a; . file` in a shell).
- `deploy/pi/install.sh`: idempotent; `uv venv --python python3`,
  `uv export --frozen --no-dev --no-hashes` to a temp file,
  `uv pip install --index https://www.piwheels.org/simple
  --index-strategy unsafe-best-match -r <that file>`. Sets
  `UV_PYTHON_DOWNLOADS=never`.
- `deploy/pi/gaming-pc-wakeup.service`: `ExecStart=<project>/.venv/bin/uvicorn
  app.main:app --host 0.0.0.0 --port 8000`, `EnvironmentFile`, `Restart=on-failure`,
  `WantedBy=multi-user.target`.
- `deploy/termux/install.sh`: `pkg install python uv rust` (idempotent) then
  `UV_PYTHON_DOWNLOADS=never uv sync --no-dev`.
- `deploy/termux/boot.sh`: `termux-wake-lock`, source the env file, exec
  `.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- `deploy/windows/sleep.ps1`: calls `powrprof.dll` `SetSuspendState(false,
  false, false)` via P/Invoke (sleep, never hibernate). Installed on the PC
  as the action of a scheduled task `gaming-pc-sleep` with no trigger,
  run on demand.
- `README.md` documents, in this order:
  - PC prerequisites: WoL enabled in BIOS/UEFI, NIC driver set to allow
    waking the computer, Windows Fast Startup disabled, Ethernet connection.
  - PC sleep over SSH (optional): enable the OpenSSH Server optional
    feature, generate an ed25519 key on the host, register the public key
    in the right `authorized_keys` file with a `command="schtasks /run /tn
    gaming-pc-sleep"` restriction, copy `sleep.ps1`, register the scheduled
    task, and test `schtasks /run` locally before testing over SSH.
  - Environment file: copy the example, fill in `WOL_MAC` and `WOL_HOST`
    (and the `WOL_SSH_*` values if sleep is wanted).
  - Host A (Pi 1): flash Raspberry Pi OS Lite 32-bit trixie, install uv
    (ARMv6 build), clone, run `deploy/pi/install.sh`, install and enable the
    service, install Tailscale from apt.
  - Host B (Note 8): install Termux and Termux:Boot from F-Droid, clone, run
    `deploy/termux/install.sh`, copy `boot.sh` to `~/.termux/boot/`, exclude
    Termux from battery optimisation, disable Wi-Fi sleep, install the
    Tailscale Android app.
  - Example `curl` commands for the three endpoints over the tailnet.

## Host gates and contingency
- Each host has a gate the user runs on the device: run
  `deploy/<host>/install.sh`, start the server, confirm `GET /health` returns
  200, and (for the phone) confirm the server is still running after the
  screen has been off overnight. Results are recorded under
  `.agent/findings/`.
- The gates do not block implementing the endpoints. The FastAPI stack is
  already known to install on the Note 8, so no stdlib fallback is planned.
- If the Pi 1 gate fails (for example no usable `pydantic-core` wheel), the
  Pi 1 is dropped from the supported hosts and `deploy/pi/` is removed.
  Nothing else changes.

## Non-goals
- No web UI.
- No multiple targets or per-request MAC addresses.
- No scheduling, shutdown, hibernate, or remote-desktop features. Sleep is
  the only power action besides wake.
- No Docker image.
- No persistent storage.

## Completion Criteria
- `uv sync` exits 0.
- `uv run ruff check .` exits 0.
- `uv run pytest -q` exits 0 with all tests passing.
- With `WOL_MAC` and `WOL_HOST` set, `uv run uvicorn app.main:app` starts;
  `GET /health`, `POST /wake`, `GET /status`, and `POST /sleep` return the
  documented responses; any other path returns 404.
- Without `WOL_MAC`, or with a half-configured or dangling `WOL_SSH_*`
  pair, the server refuses to start with a clear error.
- `deploy/common/`, `deploy/pi/`, `deploy/termux/`, and `README.md` exist
  and match the behaviour above.
- On at least one supported host: the install script completes, the server
  starts on boot, `POST /wake` from a Tailscale-connected client turns the
  gaming PC on, and (if sleep is configured) `POST /sleep` puts it to sleep
  and `GET /status` flips to `online: false`. A host that was not tried is
  marked untested in the README.
