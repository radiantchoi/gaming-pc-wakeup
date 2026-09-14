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
    )


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


def test_reads_process_environment_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("WOL_PORT", "7")
    settings = load_settings()
    assert settings.mac == MAC
    assert settings.port == 7
