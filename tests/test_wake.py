import importlib
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

MAC = bytes.fromhex("aabbccddeeff")


def _recorder(calls: list) -> Callable[[bytes, str, int], None]:
    def send(mac: bytes, broadcast: str, port: int) -> None:
        calls.append((mac, broadcast, port))

    return send


def test_wake_sends_packet_and_reports_defaults(load_main, monkeypatch) -> None:
    main = load_main()
    calls: list = []
    monkeypatch.setattr(main, "send_magic_packet", _recorder(calls))

    response = TestClient(main.app).post("/wake")

    assert response.status_code == 200
    assert response.json() == {
        "status": "sent",
        "mac": "AA:BB:CC:DD:EE:FF",
        "broadcast": "255.255.255.255",
        "port": 9,
    }
    assert calls == [(MAC, "255.255.255.255", 9)]


def test_wake_uses_configured_broadcast_and_port(load_main, monkeypatch) -> None:
    main = load_main(WOL_BROADCAST="192.168.1.255", WOL_PORT="7")
    calls: list = []
    monkeypatch.setattr(main, "send_magic_packet", _recorder(calls))

    response = TestClient(main.app).post("/wake")

    assert response.status_code == 200
    assert response.json()["broadcast"] == "192.168.1.255"
    assert response.json()["port"] == 7
    assert calls == [(MAC, "192.168.1.255", 7)]


@pytest.mark.parametrize("headers", [{}, {"X-Token": "wrong"}])
def test_wake_rejects_missing_or_wrong_token(load_main, monkeypatch, headers) -> None:
    main = load_main(WOL_TOKEN="secret")
    calls: list = []
    monkeypatch.setattr(main, "send_magic_packet", _recorder(calls))

    response = TestClient(main.app).post("/wake", headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid token"}
    assert calls == []


def test_wake_accepts_correct_token(load_main, monkeypatch) -> None:
    main = load_main(WOL_TOKEN="secret")
    calls: list = []
    monkeypatch.setattr(main, "send_magic_packet", _recorder(calls))

    response = TestClient(main.app).post("/wake", headers={"X-Token": "secret"})

    assert response.status_code == 200
    assert len(calls) == 1


def test_wake_reports_send_failure(load_main, monkeypatch) -> None:
    main = load_main()

    def fail(mac: bytes, broadcast: str, port: int) -> None:
        raise OSError("network is unreachable")

    monkeypatch.setattr(main, "send_magic_packet", fail)

    response = TestClient(main.app).post("/wake")

    assert response.status_code == 502
    assert response.json() == {"detail": "network is unreachable"}


def test_get_wake_not_allowed(load_main) -> None:
    response = TestClient(load_main().app).get("/wake")
    assert response.status_code == 405


def test_startup_fails_without_mac(load_main, monkeypatch) -> None:
    main = load_main()
    monkeypatch.delenv("WOL_MAC")
    with pytest.raises(ValueError, match="WOL_MAC"):
        importlib.reload(main)
