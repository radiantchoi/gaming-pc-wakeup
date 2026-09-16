#!/bin/sh
# Install gaming-pc-wakeup on a Raspberry Pi 1 (ARMv6, 32-bit Pi OS).
#
# PyPI has no ARMv6 wheels for pydantic-core, so this script installs the
# versions pinned in uv.lock with piwheels as an additional index. This is
# the only place the project knows about piwheels. Safe to re-run.
set -eu

cd "$(dirname "$0")/../.."

# uv has no managed CPython build for ARMv6; always use the OS interpreter.
export UV_PYTHON_DOWNLOADS=never

if [ ! -d .venv ]; then
    uv venv --python python3
fi

req="$(mktemp)"
trap 'rm -f "$req"' EXIT

uv export --frozen --no-dev --no-hashes -o "$req"
uv pip install \
    --index https://www.piwheels.org/simple \
    --index-strategy unsafe-best-match \
    -r "$req"

echo "Installed. Start with: .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000"
