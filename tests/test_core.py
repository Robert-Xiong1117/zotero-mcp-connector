import os
import subprocess
import sys
import time
import urllib.request

import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    yield


def test_config_roundtrip_and_secrets():
    from app import config as c
    cfg = c.load()
    assert not cfg.configured
    cfg.ngrok_authtoken = "tok"
    cfg.domain = c.normalize_domain("https://abc.ngrok-free.dev/mcp")
    cfg.ensure_secrets()
    c.save(cfg)
    again = c.load()
    assert again.domain == "abc.ngrok-free.dev"
    assert again.configured and len(again.admin_password) > 30 and again.basic_user.startswith("zotero-")


def test_policy_contains_whitelist_and_basic_auth():
    from app import config as c, ngrok
    cfg = c.Config(ngrok_authtoken="t", domain="x.ngrok-free.dev")
    cfg.ensure_secrets()
    cfg.auth_mode_ip, cfg.auth_mode_until = "1.2.3.4", time.time() + 60
    text = ngrok.write_policy(cfg).read_text()
    assert "160.79.104.0/21" in text and "1.2.3.4/32" in text
    assert "req.url.path.startsWith('/authorize')" in text
    assert f"{cfg.basic_user}:{cfg.basic_password}" in text
    cfg.auth_mode_until = time.time() - 1
    assert "1.2.3.4" not in ngrok.write_policy(cfg).read_text()


def test_backup_roundtrip(tmp_path):
    from app import backup, config as c
    from app.paths import oauth_db_path
    cfg = c.Config(ngrok_authtoken="t", domain="x.ngrok-free.dev"); cfg.ensure_secrets(); c.save(cfg)
    oauth_db_path().parent.mkdir(parents=True, exist_ok=True); oauth_db_path().write_bytes(b"db")
    blob = backup.export_bundle("correct horse")
    with pytest.raises(ValueError):
        backup.import_bundle(blob, "wrong pass")
    c.config_path().unlink(); oauth_db_path().unlink()
    backup.import_bundle(blob, "correct horse")
    assert c.load().admin_password == cfg.admin_password
    assert oauth_db_path().read_bytes() == b"db"


def test_legacy_import(tmp_path):
    from app import config as c
    d = tmp_path / "legacy"; d.mkdir()
    (d / ".env").write_text("ZOTERO_MCP_ADMIN_PASSWORD=abc\nZOTERO_MCP_PUBLIC_URL=https://foo.ngrok-free.dev\n")
    (d / "ngrok-policy.yml").write_text('credentials:\n            - "zotero-1a2b3c:secretpw"\n')
    cfg = c.import_legacy(str(d))
    assert (cfg.domain, cfg.admin_password, cfg.basic_user, cfg.basic_password) == \
        ("foo.ngrok-free.dev", "abc", "zotero-1a2b3c", "secretpw")


def test_server_child_requires_auth(tmp_path):
    """The bundled zotero-mcp-lite starts via 'serve-mcp' and rejects unauthenticated requests."""
    env = dict(os.environ, ZOTERO_MCP_ADMIN_PASSWORD="x" * 40, ZOTERO_MCP_PUBLIC_URL="https://x.ngrok-free.dev")
    p = subprocess.Popen([sys.executable, "-m", "app", "serve-mcp", "serve", "--transport", "streamable-http",
                          "--host", "127.0.0.1", "--port", "18765"], env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        code = 0
        for _ in range(60):
            try:
                urllib.request.build_opener(urllib.request.ProxyHandler({})).open("http://127.0.0.1:18765/mcp", timeout=2)
            except urllib.error.HTTPError as e:
                code = e.code; break
            except Exception:
                time.sleep(1)
        assert code == 401
    finally:
        p.kill()


def test_icon_renders():
    from app.icons import make_icon
    assert make_icon("ok", 64).size == (64, 64)
