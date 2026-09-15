"""Wake-on-LAN helpers built on the standard library only."""

import re
import socket

_HEX12 = re.compile(r"[0-9A-Fa-f]{12}")
_MAC_LEN = 6


def parse_mac(value: str) -> bytes:
    """Parse a MAC address into 6 bytes.

    Accepts ``AA:BB:CC:DD:EE:FF``, ``AA-BB-CC-DD-EE-FF`` and
    ``AABBCCDDEEFF`` in any case. Raises ``ValueError`` otherwise.
    """
    text = value.strip()
    for sep in (":", "-"):
        if sep in text:
            parts = text.split(sep)
            if len(parts) != _MAC_LEN or any(len(p) != 2 for p in parts):
                raise ValueError(f"invalid MAC address: {value!r}")
            text = "".join(parts)
            break
    if not _HEX12.fullmatch(text):
        raise ValueError(f"invalid MAC address: {value!r}")
    return bytes.fromhex(text)


def format_mac(mac: bytes) -> str:
    """Format 6 bytes as an upper-case, colon-separated MAC address."""
    _check_mac(mac)
    return ":".join(f"{b:02X}" for b in mac)


def build_magic_packet(mac: bytes) -> bytes:
    """Return the 102-byte WoL magic packet for ``mac``."""
    _check_mac(mac)
    return b"\xff" * 6 + mac * 16


def send_magic_packet(mac: bytes, broadcast: str, port: int) -> None:
    """Send one magic packet for ``mac`` as a UDP broadcast."""
    packet = build_magic_packet(mac)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast, port))


def is_port_open(host: str, port: int, timeout: float) -> bool:
    """Return True if a TCP connection to ``host:port`` succeeds within ``timeout``."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _check_mac(mac: bytes) -> None:
    if len(mac) != _MAC_LEN:
        raise ValueError(f"MAC must be {_MAC_LEN} bytes, got {len(mac)}")
