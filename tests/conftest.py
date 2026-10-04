"""Testinställningar: isolera historik och inställningar från användarens riktiga filer."""
import pytest


@pytest.fixture(autouse=True)
def _isolera_anvandarfiler(tmp_path, monkeypatch):
    """Historiken och inställningarna ska aldrig röra ~/.audiobook-goodreads i tester."""
    from ags import history as history_mod
    from ags import settings as settings_mod

    monkeypatch.setattr(history_mod, "DEFAULT_PATH", str(tmp_path / "history.json"))
    monkeypatch.setenv("AGS_SETTINGS", str(tmp_path / "settings.json"))
    yield
