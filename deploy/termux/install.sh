#!/data/data/com.termux/files/usr/bin/sh
# Install gaming-pc-wakeup inside Termux on an Android phone.
#
# rust is needed because PyPI's manylinux wheels do not run on Android's
# bionic libc; pydantic-core is built from source once and cached by uv.
# openssh provides the ssh client used by POST /sleep. Safe to re-run.
set -eu

pkg install -y python uv rust openssh

cd "$(dirname "$0")/../.."

# uv has no managed CPython build for Android; always use Termux's python.
UV_PYTHON_DOWNLOADS=never uv sync --no-dev

echo "Installed. Copy deploy/termux/boot.sh to ~/.termux/boot/ to start on boot."
