import importlib
from collections.abc import Callable
from types import ModuleType

import pytest

BASE_ENV = {"WOL_MAC": "aa:bb:cc:dd:ee:ff", "WOL_HOST": "192.0.2.10"}


@pytest.fixture
def load_main(monkeypatch: pytest.MonkeyPatch) -> Callable[..., ModuleType]:
    """Return a loader that sets WOL_* env vars and (re)imports ``app.main``."""

    def _load(**env: str) -> ModuleType:
        for name, value in {**BASE_ENV, **env}.items():
            monkeypatch.setenv(name, value)
        import app.main

        return importlib.reload(app.main)

    return _load
