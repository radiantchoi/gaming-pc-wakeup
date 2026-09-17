"""Put the gaming PC to sleep by triggering a scheduled task over SSH."""

import subprocess

REMOTE_COMMAND = "schtasks /run /tn gaming-pc-sleep"


def build_ssh_argv(host: str, user: str, key: str, port: int) -> list[str]:
    return [
        "ssh",
        "-i",
        key,
        "-p",
        str(port),
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "StrictHostKeyChecking=accept-new",
        f"{user}@{host}",
        REMOTE_COMMAND,
    ]


def request_sleep(host: str, user: str, key: str, port: int, timeout: float) -> None:
    """Run the sleep task on ``host`` via ssh; raise ``RuntimeError`` on any failure."""
    argv = build_ssh_argv(host, user, key, port)
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError:
        raise RuntimeError("ssh client not found") from None
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ssh timed out after {timeout}s") from None
    if result.returncode != 0:
        message = result.stderr.strip() or f"ssh exited with {result.returncode}"
        raise RuntimeError(message)
