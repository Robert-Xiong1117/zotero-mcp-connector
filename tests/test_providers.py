"""ChatGPT allow-list: download/validation, refresh rules, policy output, panel switch."""
import json
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app import providers

GOOD = {"creationTime": "2026-11-06T18:26:55", "prefixes":
        [{"ipv4Prefix": f"20.0.{i}.0/24"} for i in range(12)]
        + [{"ipv4Prefix": "20.0.0.0/24"}, {"ipv6Prefix": "2603:1000::/40"}, {"ipv4Prefix": "not-an-ip"}, {}]}


def serve(body, status=200):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            b = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}/list.json"


def test_fetch_validates_and_dedupes():
    httpd, url = serve(GOOD)
    try:
        created, cidrs = providers.fetch_openai(url)
    finally:
        httpd.shutdown()
    assert created == "2026-11-06T18:26:55"
    assert len(cidrs) == 13 and cidrs[-1] == "2603:1000::/40" and "not-an-ip" not in cidrs


@pytest.mark.parametrize("body,status", [({"prefixes": [{"ipv4Prefix": "1.2.3.0/24"}]}, 200), (b"<html>", 200), (b"x", 500)])
def test_fetch_rejects_broken_lists(body, status):
    httpd, url = serve(body, status)
    try:
        with pytest.raises(providers.ProviderError):
            providers.fetch_openai(url)
    finally:
        httpd.shutdown()


def _cfg(**kw):
    from app.config import Config
    return Config(ngrok_authtoken="t", domain="x.ngrok-free.dev", **kw)


def test_refresh_rules():
    calls = []

    def fetch():
        calls.append(1)
        return "T2", ["20.0.1.0/24", "20.0.2.0/24"]

    cfg = _cfg()
    assert providers.refresh_openai(cfg, fetch=fetch) is False and not calls          # disabled: never downloads
    cfg.openai_enabled = True
    assert providers.refresh_openai(cfg, fetch=fetch) is True and cfg.openai_list_time == "T2"
    assert providers.refresh_openai(cfg, fetch=fetch) is False and len(calls) == 1    # fresh: not due
    assert providers.refresh_openai(cfg, force=True, fetch=fetch) is False and len(calls) == 2   # same list

    def broken():
        raise providers.ProviderError("down")
    cfg.openai_checked_at = 0
    assert providers.refresh_openai(cfg, fetch=broken) is False                      # keeps last good list
    assert cfg.openai_cidrs == ["20.0.1.0/24", "20.0.2.0/24"]
    with pytest.raises(providers.ProviderError):
        providers.refresh_openai(_cfg(openai_enabled=True), fetch=broken)              # nothing to fall back to


def test_policy_includes_chatgpt_only_when_enabled():
    from app import ngrok
    cfg = _cfg(openai_cidrs=["20.0.1.0/24"]); cfg.ensure_secrets()
    assert "20.0.1.0/24" not in ngrok.write_policy(cfg).read_text()
    cfg.openai_enabled = True
    text = ngrok.write_policy(cfg).read_text()
    assert "160.79.104.0/21" in text and "            - 20.0.1.0/24" in text
    assert "basic-auth" in text                                                        # login protection unchanged


def test_panel_switch_and_status(monkeypatch):
    from app import config as c
    from app.services import Services
    from app.web import TOKEN, Panel
    monkeypatch.setenv("ZMC_ZOTERO_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(providers, "fetch_openai", lambda: ("T9", [f"20.1.{i}.0/24" for i in range(15)]))
    c.save(c.Config())                                   # not configured: switching must not touch any tunnel
    svc = Services()
    panel = Panel(svc); panel.serve()
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def post(enabled):
        req = urllib.request.Request(f"http://127.0.0.1:{panel.port}/api/providers", method="POST",
                                     data=json.dumps({"openai": enabled}).encode(),
                                     headers={"X-Token": TOKEN, "Content-Type": "application/json"})
        return json.loads(op.open(req, timeout=10).read())
    try:
        assert post(True)["openai"] == {"enabled": True, "count": 15, "list_time": "T9"}
        assert c.load().openai_enabled and svc.status()["openai"]["count"] == 15
        assert post(False)["openai"]["enabled"] is False and not c.load().openai_enabled

        def down():
            raise providers.ProviderError("ChatGPT IP 列表下载失败")
        monkeypatch.setattr(providers, "fetch_openai", down)
        c.save(c.Config())
        req = urllib.request.Request(f"http://127.0.0.1:{panel.port}/api/providers", method="POST",
                                     data=b'{"openai": true}', headers={"X-Token": TOKEN})
        with pytest.raises(urllib.error.HTTPError) as e:
            op.open(req, timeout=10)
        assert e.value.code == 400 and not c.load().openai_enabled                       # stays off, clear error
    finally:
        panel.httpd.shutdown()
