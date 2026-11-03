import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Keep every test away from the real config, ngrok policy and OAuth database (all platforms)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    monkeypatch.setenv("ZMC_CONFIG_DIR", str(tmp_path / "cfg" / "ZoteroMCP"))
    monkeypatch.setenv("ZMC_OAUTH_DB", str(tmp_path / "data" / "zotero-mcp" / "oauth.sqlite"))
    from app.paths import config_dir, oauth_db_path
    for p in (config_dir(), oauth_db_path()):
        if tmp_path not in p.parents:
            pytest.fail(f"test isolation broken: {p} is outside {tmp_path}")
    yield
