import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import sleep as sleep_module
from app.sleep import build_ssh_argv, request_sleep

EXPECTED_ARGV = [
    "ssh",
    "-i",
    "/keys/pc",
    "-p",
    "22",
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=5",
    "-o",
    "StrictHostKeyChecking=accept-new",
    "gamer@192.0.2.10",
    "schtasks /run /tn gaming-pc-sleep",
]


def _fake_run(calls: list, returncode: int = 0, stderr: str = ""):
    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, returncode, stdout="", stderr=stderr)

    return run


def test_build_ssh_argv() -> None:
    assert build_ssh_argv("192.0.2.10", "gamer", "/keys/pc", 22) == EXPECTED_ARGV


def test_request_sleep_runs_ssh_with_timeout(monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(subprocess, "run", _fake_run(calls))

    request_sleep("192.0.2.10", "gamer", "/keys/pc", 22, 7.5)

    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv == EXPECTED_ARGV
    assert kwargs["timeout"] == 7.5
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True


def test_request_sleep_reports_stderr_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(subprocess, "run", _fake_run([], 255, "Permission denied (publickey).\n"))
    with pytest.raises(RuntimeError, match=r"^Permission denied \(publickey\)\.$"):
        request_sleep("192.0.2.10", "gamer", "/keys/pc", 22, 10.0)


def test_request_sleep_reports_exit_code_when_stderr_empty(monkeypatch) -> None:
    monkeypatch.setattr(subprocess, "run", _fake_run([], 1))
    with pytest.raises(RuntimeError, match="ssh exited with 1"):
        request_sleep("192.0.2.10", "gamer", "/keys/pc", 22, 10.0)


def test_request_sleep_reports_missing_ssh(monkeypatch) -> None:
    def run(argv, **kwargs):
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(RuntimeError, match="ssh client not found"):
        request_sleep("192.0.2.10", "gamer", "/keys/pc", 22, 10.0)


def test_request_sleep_reports_timeout(monkeypatch) -> None:
    def run(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(RuntimeError, match="ssh timed out after 3.0s"):
        request_sleep("192.0.2.10", "gamer", "/keys/pc", 22, 3.0)


@pytest.fixture
def key_file(tmp_path: Path) -> str:
    path = tmp_path / "pc"
    path.write_text("not a real key")
    return str(path)


def _recorder(calls: list):
    def request(host: str, user: str, key: str, port: int, timeout: float) -> None:
        calls.append((host, user, key, port, timeout))

    return request


def test_sleep_unconfigured_returns_503(load_main, monkeypatch) -> None:
    main = load_main()
    calls: list = []
    monkeypatch.setattr(main, "request_sleep", _recorder(calls))

    response = TestClient(main.app).post("/sleep")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "sleep is not configured: set WOL_SSH_USER and WOL_SSH_KEY"
    }
    assert calls == []


def test_sleep_calls_ssh_with_settings(load_main, monkeypatch, key_file: str) -> None:
    main = load_main(
        WOL_SSH_USER="gamer", WOL_SSH_KEY=key_file, WOL_SSH_PORT="2222", WOL_SSH_TIMEOUT="4"
    )
    calls: list = []
    monkeypatch.setattr(main, "request_sleep", _recorder(calls))

    response = TestClient(main.app).post("/sleep")

    assert response.status_code == 200
    assert response.json() == {"status": "sleeping", "host": "192.0.2.10"}
    assert calls == [("192.0.2.10", "gamer", key_file, 2222, 4.0)]


@pytest.mark.parametrize("headers", [{}, {"X-Token": "wrong"}])
def test_sleep_rejects_bad_token(load_main, monkeypatch, key_file: str, headers) -> None:
    main = load_main(WOL_SSH_USER="gamer", WOL_SSH_KEY=key_file, WOL_TOKEN="secret")
    calls: list = []
    monkeypatch.setattr(main, "request_sleep", _recorder(calls))

    response = TestClient(main.app).post("/sleep", headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid token"}
    assert calls == []


def test_sleep_reports_ssh_failure(load_main, monkeypatch, key_file: str) -> None:
    main = load_main(WOL_SSH_USER="gamer", WOL_SSH_KEY=key_file)

    def fail(*args) -> None:
        raise RuntimeError("Connection refused")

    monkeypatch.setattr(main, "request_sleep", fail)

    response = TestClient(main.app).post("/sleep")

    assert response.status_code == 502
    assert response.json() == {"detail": "Connection refused"}


def test_get_sleep_not_allowed(load_main) -> None:
    assert TestClient(load_main().app).get("/sleep").status_code == 405


def test_module_constant_matches_argv() -> None:
    assert EXPECTED_ARGV[-1] == sleep_module.REMOTE_COMMAND
