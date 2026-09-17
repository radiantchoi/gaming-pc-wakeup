"""Configuration read from environment variables (see SPEC.md)."""

import os
from collections.abc import Mapping
from dataclasses import dataclass

from app.wol import parse_mac


@dataclass(frozen=True)
class Settings:
    mac: bytes
    broadcast: str
    port: int
    host: str
    status_port: int
    status_timeout: float
    token: str | None
    ssh_user: str | None
    ssh_key: str | None
    ssh_port: int
    ssh_timeout: float

    @property
    def sleep_configured(self) -> bool:
        return self.ssh_user is not None and self.ssh_key is not None


def load_settings(env: Mapping[str, str] = os.environ) -> Settings:
    """Build ``Settings`` from ``env``; raise ``ValueError`` naming the bad variable."""
    mac_text = env.get("WOL_MAC")
    if not mac_text:
        raise ValueError("WOL_MAC is required")
    try:
        mac = parse_mac(mac_text)
    except ValueError as exc:
        raise ValueError(f"WOL_MAC is invalid: {exc}") from None

    host = env.get("WOL_HOST")
    if not host:
        raise ValueError("WOL_HOST is required")

    ssh_user = env.get("WOL_SSH_USER") or None
    ssh_key = env.get("WOL_SSH_KEY") or None
    if ssh_user is not None and ssh_key is None:
        raise ValueError("WOL_SSH_KEY is required when WOL_SSH_USER is set")
    if ssh_key is not None and ssh_user is None:
        raise ValueError("WOL_SSH_USER is required when WOL_SSH_KEY is set")
    if ssh_key is not None and not os.path.isfile(ssh_key):
        raise ValueError(f"WOL_SSH_KEY file not found: {ssh_key}")

    return Settings(
        mac=mac,
        broadcast=env.get("WOL_BROADCAST", "255.255.255.255"),
        port=_get_int(env, "WOL_PORT", 9),
        host=host,
        status_port=_get_int(env, "WOL_STATUS_PORT", 3389),
        status_timeout=_get_float(env, "WOL_STATUS_TIMEOUT", 1.0),
        token=env.get("WOL_TOKEN") or None,
        ssh_user=ssh_user,
        ssh_key=ssh_key,
        ssh_port=_get_int(env, "WOL_SSH_PORT", 22),
        ssh_timeout=_get_float(env, "WOL_SSH_TIMEOUT", 10.0),
    )


def _get_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from None


def _get_float(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"{name} must be a number, got {raw!r}") from None
