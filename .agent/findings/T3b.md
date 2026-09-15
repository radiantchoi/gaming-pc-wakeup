# T3b — Make the toolchain host-neutral (implemented and verified by orchestrator)

- Performed by: orchestrator (Claude Fable 5.1) directly, at the user's request
- Completed: 2026-09-16
- Supersedes T3. Trigger: a second host (Galaxy Note 8 + Termux, aarch64/Android, Python 3.14, Rust installed) was added alongside the Pi 1. The user asked that host-specific accommodations be isolated in one place away from the shared code.

## What was done
- `pyproject.toml`: removed `[[tool.uv.index]] piwheels`, `[tool.uv.sources] pydantic-core`, and the `pydantic-core` direct dependency. Dependencies are back to exactly fastapi, uvicorn (dev: httpx, pytest, ruff). Restored the trailing newline.
- Deleted `.python-version` (was `3.13`, Pi-specific; Termux has 3.14 and uv cannot download 3.13 there).
- Regenerated `uv.lock` from scratch (`rm uv.lock && uv lock`) because uv preserves old resolution forks across re-locks; the top-level `resolution-markers` fork on `platform_machine` is now gone.
- The piwheels workaround moves to `deploy/pi/install.sh` (T10): `uv venv --python python3`, `uv export --frozen --no-dev --no-hashes`, `uv pip install --index https://www.piwheels.org/simple --index-strategy unsafe-best-match -r <exported>`. The systemd unit and the Termux boot script both run `.venv/bin/uvicorn` directly, so uv is not involved at runtime.
- `SPEC.md`: "Deployment context" now has a common part plus "Host A: Raspberry Pi 1 Model B" and "Host B: Galaxy Note 8 with Termux"; deploy layout is `deploy/common/`, `deploy/pi/`, `deploy/termux/`; the stdlib contingency was replaced by "drop the Pi if its gate fails" since FastAPI is known to install on the Note 8.
- `.agent/plan.md`: T5 split into T5-pi and T5-termux (both human, non-blocking for T6–T10); T10 and T11 rewritten per host.

## Side effect of regenerating the lock
Three packages moved to newer releases available today: anyio 4.14.2 → 4.15.1, ruff 0.16.5 → 0.16.7, uvicorn 0.52.4 → 0.53.0. Tests pass. pytest now shows a second upstream warning (starlette uses a deprecated anyio alias); not blocking.

## Acceptance criteria
| Criterion | Result | Evidence |
|---|---|---|
| `pyproject.toml` has exactly fastapi, uvicorn (dev: httpx, pytest, ruff) and no `tool.uv` table | PASS | file contents |
| no `.python-version` | PASS | `git rm` |
| `uv.lock` has no piwheels entries and no `resolution-markers` | PASS | both grep counts 0 |
| `uv sync`, `uv run ruff check .`, `uv run pytest -q` pass | PASS | 30 passed, 2 warnings; ruff clean |
| `uv export --frozen --no-dev --no-hashes` works (input for the Pi script) | PASS | lists fastapi, pydantic-core 2.46.5, starlette, uvicorn |

## Not yet verified
Whether `uv pip install` with the piwheels index picks the `linux_armv6l` wheel on the Pi 1. That is T5-pi.
