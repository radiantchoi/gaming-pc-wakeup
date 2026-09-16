#!/data/data/com.termux/files/usr/bin/sh
# Termux:Boot start script for gaming-pc-wakeup.
# Copy to ~/.termux/boot/gaming-pc-wakeup.sh (must be executable).
# Expects the repo at $HOME/gaming-pc-wakeup and the env file at
# $HOME/gaming-pc-wakeup.env (see deploy/common/gaming-pc-wakeup.env.example).
set -eu

termux-wake-lock

cd "$HOME/gaming-pc-wakeup"

set -a
. "$HOME/gaming-pc-wakeup.env"
set +a

exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 \
    >> "$HOME/gaming-pc-wakeup.log" 2>&1
