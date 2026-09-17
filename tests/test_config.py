import pytest

from app.config import Settings, load_settings

REQUIRED = {"WOL_MAC": "aa:bb:cc:dd:ee:ff", "WOL_HOST": "192.0.2.10"}
MAC = bytes.fromhex("aabbccddeeff")


def test_defaults_applied() -> None:
    settings = load_settings(REQUIRED)
    assert settings == Settings(
        mac=MAC,
        broadcast="255.255.255.255",
        port=9,
        host="192.0.2.10",
        status_port=3389,
        status_timeout=1.0,
        token=None,
        ssh_user=None,
        ssh_key=None,
        ssh_port=22,
        ssh_timeout=10.0,
    )
    assert settings.sleep_configured is False


def test_custom_values_parsed() -> None:
    env = {
        **REQUIRED,
        "WOL_BROADCAST": "192.168.1.255",
        "WOL_PORT": "7",
        "WOL_STATUS_PORT": "22",
        "WOL_STATUS_TIMEOUT": "0.5",
        "WOL_TOKEN": "secret",
    }
    settings = load_settings(env)
    assert settings.broadcast == "192.168.1.255"
    assert settings.port == 7
    assert settings.status_port == 22
    assert settings.status_timeout == 0.5
    assert settings.token == "secret"


@pytest.mark.parametrize("missing", ["WOL_MAC", "WOL_HOST"])
def test_missing_required_names_variable(missing: str) -> None:
    env = {k: v for k, v in REQUIRED.items() if k != missing}
    with pytest.raises(ValueError, match=missing):
        load_settings(env)


@pytest.mark.parametrize("missing", ["WOL_MAC", "WOL_HOST"])
def test_empty_required_names_variable(missing: str) -> None:
    env = {**REQUIRED, missing: ""}
    with pytest.raises(ValueError, match=missing):
        load_settings(env)


def test_invalid_mac_names_variable() -> None:
    with pytest.raises(ValueError, match="WOL_MAC"):
        load_settings({**REQUIRED, "WOL_MAC": "not-a-mac"})


@pytest.mark.parametrize(
    ("name", "value"),
    [("WOL_PORT", "nine"), ("WOL_STATUS_PORT", "3.5"), ("WOL_STATUS_TIMEOUT", "fast")],
)
def test_invalid_numbers_name_variable(name: str, value: str) -> None:
    with pytest.raises(ValueError, match=name):
        load_settings({**REQUIRED, name: value})


def test_empty_token_means_no_auth() -> None:
    assert load_settings({**REQUIRED, "WOL_TOKEN": ""}).token is None


def test_ssh_values_parsed(tmp_path) -> None:
    key = tmp_path / "pc"
    key.write_text("key")
    env = {
        **REQUIRED,
        "WOL_SSH_USER": "gamer",
        "WOL_SSH_KEY": str(key),
        "WOL_SSH_PORT": "2222",
        "WOL_SSH_TIMEOUT": "4",
    }
    settings = load_settings(env)
    assert settings.sleep_configured is True
    assert settings.ssh_user == "gamer"
    assert settings.ssh_key == str(key)
    assert settings.ssh_port == 2222
    assert settings.ssh_timeout == 4.0


def test_ssh_user_without_key_names_key(tmp_path) -> None:
    with pytest.raises(ValueError, match="WOL_SSH_KEY"):
        load_settings({**REQUIRED, "WOL_SSH_USER": "gamer"})


def test_ssh_key_without_user_names_user(tmp_path) -> None:
    key = tmp_path / "pc"
    key.write_text("key")
    with pytest.raises(ValueError, match="WOL_SSH_USER"):
        load_settings({**REQUIRED, "WOL_SSH_KEY": str(key)})


def test_ssh_key_missing_file_names_key(tmp_path) -> None:
    with pytest.raises(ValueError, match="WOL_SSH_KEY"):
        load_settings({**REQUIRED, "WOL_SSH_USER": "gamer", "WOL_SSH_KEY": str(tmp_path / "nope")})


@pytest.mark.parametrize(("name", "value"), [("WOL_SSH_PORT", "x"), ("WOL_SSH_TIMEOUT", "y")])
def test_invalid_ssh_numbers_name_variable(name: str, value: str) -> None:
    with pytest.raises(ValueError, match=name):
        load_settings({**REQUIRED, name: value})


def test_reads_process_environment_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("WOL_PORT", "7")
    settings = load_settings()
    assert settings.mac == MAC
    assert settings.port == 7
