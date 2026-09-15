import socket

import pytest
from fastapi.testclient import TestClient

from app.wol import is_port_open


@pytest.mark.parametrize("online", [True, False])
def test_status_reports_probe_result(load_main, monkeypatch, online: bool) -> None:
    main = load_main(WOL_STATUS_PORT="22", WOL_STATUS_TIMEOUT="0.25")
    probes: list = []

    def probe(host: str, port: int, timeout: float) -> bool:
        probes.append((host, port, timeout))
        return online

    monkeypatch.setattr(main, "is_port_open", probe)

    response = TestClient(main.app).get("/status")

    assert response.status_code == 200
    assert response.json() == {"online": online, "host": "192.0.2.10", "port": 22}
    assert probes == [("192.0.2.10", 22, 0.25)]


def test_is_port_open_true_for_listening_socket() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        assert is_port_open("127.0.0.1", port, 1.0) is True


def test_is_port_open_false_for_closed_port() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    assert is_port_open("127.0.0.1", port, 1.0) is False
