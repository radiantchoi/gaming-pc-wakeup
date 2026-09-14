import socket

import pytest

from app.wol import build_magic_packet, format_mac, parse_mac, send_magic_packet

MAC = bytes.fromhex("aabbccddeeff")


@pytest.mark.parametrize(
    "value",
    ["AA:BB:CC:DD:EE:FF", "aa:bb:cc:dd:ee:ff", "AA-BB-CC-DD-EE-FF", "aabbccddeeff", "AABBCCDDEEFF"],
)
def test_parse_mac_accepts_all_formats(value: str) -> None:
    assert parse_mac(value) == MAC


@pytest.mark.parametrize(
    "value",
    [
        "",
        "AA:BB:CC:DD:EE",
        "AA:BB:CC:DD:EE:FF:00",
        "GG:BB:CC:DD:EE:FF",
        "AABBCCDDEEF",
        "AABBCCDDEEFFA",
        "AA:BB-CC:DD:EE:FF",
        "AABBCCDDEE  ",
    ],
)
def test_parse_mac_rejects_invalid(value: str) -> None:
    with pytest.raises(ValueError):
        parse_mac(value)


def test_format_mac_round_trips() -> None:
    assert format_mac(MAC) == "AA:BB:CC:DD:EE:FF"
    assert parse_mac(format_mac(MAC)) == MAC


def test_build_magic_packet_layout() -> None:
    packet = build_magic_packet(MAC)
    assert len(packet) == 102
    assert packet[:6] == b"\xff" * 6
    assert packet[6:] == MAC * 16


def test_build_magic_packet_rejects_wrong_length() -> None:
    with pytest.raises(ValueError):
        build_magic_packet(b"\x00" * 5)


def test_send_magic_packet_delivers_to_loopback() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
        receiver.bind(("127.0.0.1", 0))
        receiver.settimeout(2)
        port = receiver.getsockname()[1]
        send_magic_packet(MAC, "127.0.0.1", port)
        data, _ = receiver.recvfrom(1024)
    assert data == build_magic_packet(MAC)
