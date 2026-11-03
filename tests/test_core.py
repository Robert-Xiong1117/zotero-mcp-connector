import os
import subprocess
import sys
import time
import urllib.request

import pytest


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
    # platformdirs ignores env vars on Windows: patch it so the child never opens the real oauth.sqlite
    env["ZMC_TEST_DATA"] = str(tmp_path / "data")
    boot = ("import os, sys, platformdirs; platformdirs.user_data_dir = lambda *a, **k: os.environ['ZMC_TEST_DATA']; "
            "sys.argv = ['app'] + sys.argv[1:]; from app.__main__ import main; main()")
    p = subprocess.Popen([sys.executable, "-c", boot, "serve-mcp", "serve", "--transport", "streamable-http",
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


def test_bridge_token_generated_once():
    from app import config as c
    cfg = c.Config(); cfg.ensure_secrets()
    tok = cfg.zmc_bridge_token
    assert tok.startswith("zmc-") and len(tok) > 30
    cfg.ensure_secrets()
    assert cfg.zmc_bridge_token == tok
    old = c.Config(**{k: v for k, v in c.asdict(cfg).items() if k != "zmc_bridge_token"})   # pre-1.2.0 config
    assert old.zmc_bridge_token == ""


def test_status_and_panel_report_bridge(monkeypatch):
    import json as _json
    from app import config as c
    from app.services import Services
    from app.web import TOKEN, Panel
    monkeypatch.setenv("ZMC_ZOTERO_URL", "http://127.0.0.1:9")      # nothing listens: Zotero "offline"
    cfg = c.Config(ngrok_authtoken="t", domain="x.ngrok-free.dev"); cfg.ensure_secrets(); c.save(cfg)
    assert Services().status()["bridge"]["state"] == "offline"
    panel = Panel(None); panel.serve()
    try:
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req = urllib.request.Request(f"http://127.0.0.1:{panel.port}/api/bridge", headers={"X-Token": TOKEN})
        r = _json.loads(op.open(req, timeout=5).read())
        assert r["token"] == cfg.zmc_bridge_token and r["ping"]["state"] == "offline"
        page = op.open(urllib.request.Request(f"http://127.0.0.1:{panel.port}/", headers={"X-Token": TOKEN})).read().decode()
        assert "Zotero 桥接插件" in page and "ZoteroMCP-Bridge-1.2.0.xpi" in page and "__VERSION__" not in page
        with pytest.raises(urllib.error.HTTPError):
            op.open(f"http://127.0.0.1:{panel.port}/api/bridge", timeout=5)          # no panel token
    finally:
        panel.httpd.shutdown()
