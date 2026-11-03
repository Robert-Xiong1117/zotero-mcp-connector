"""Bridge client against a mock plugin: token check, error states, and the full highlight flow."""
import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pymupdf
import pytest

from app import bridge

TOKEN = "bridge-test-token"


class MockZotero:
    """Mimics Zotero's server: our endpoints check X-ZMC-Token; unknown paths get Zotero's plain-text 404."""

    def __init__(self, installed=True):
        self.installed, self.posts = installed, []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _reply(self, code, obj, ctype="application/json"):
                b = (json.dumps(obj) if ctype == "application/json" else obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def _handle(self):
                if not (outer.installed and self.path.startswith("/zmc/")):
                    return self._reply(404, "No endpoint found", "text/plain")
                if self.headers.get("X-ZMC-Token") != TOKEN:
                    return self._reply(403, {"error": "invalid or missing X-ZMC-Token"})
                n = int(self.headers.get("Content-Length") or 0)
                data = json.loads(self.rfile.read(n) or b"{}")
                outer.posts.append((self.path, data))
                if self.path == "/zmc/ping":
                    return self._reply(200, {"ok": True, "version": "1.2.0", "zotero": "7.0.11"})
                if self.path == "/zmc/annotate":
                    return self._reply(200, {"ok": True, "key": "ANNO0001", "attachmentKey": data["attachmentKey"]})
                if self.path == "/zmc/find-pdf":
                    return self._reply(200, {"ok": True, "found": True, "already": False,
                                             "attachmentKey": "PDF00001", "filename": "x.pdf"})

            do_GET = do_POST = _handle

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()


@pytest.fixture
def zotero(monkeypatch):
    z = MockZotero()
    monkeypatch.setenv("ZMC_ZOTERO_URL", z.url)
    monkeypatch.setenv("ZMC_BRIDGE_TOKEN", TOKEN)
    yield z
    z.httpd.shutdown()


class FakeZot:
    def __init__(self, pdf_path):
        self.pdf_path = pdf_path

    def item(self, key):
        return {"data": {"key": key, "itemType": "journalArticle"}}

    def children(self, key):
        return [{"data": {"key": "NOTE0001", "itemType": "note"}},
                {"data": {"key": "ATT00001", "itemType": "attachment", "contentType": "application/pdf",
                          "linkMode": "linked_file", "path": self.pdf_path}}]


@pytest.fixture
def pdf(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 100), "Range anxiety remains the main barrier", fontsize=11)
    page.insert_text((72, 120), "to electric vehicle adoption in China.", fontsize=11)
    p = tmp_path / "paper.pdf"
    doc.save(p)
    return str(p)


def test_ping_states(zotero, monkeypatch):
    assert bridge.ping() == {"state": "ok", "version": "1.2.0", "zotero": "7.0.11"}
    assert bridge.ping(token="wrong")["state"] == "forbidden"
    assert bridge.ping(token="")["state"] == "no-token"
    zotero.installed = False
    assert bridge.ping()["state"] == "missing"
    zotero.httpd.shutdown(); zotero.httpd.server_close()
    assert bridge.ping()["state"] == "offline"


def test_token_header_is_sent_on_every_call(zotero):
    bridge.find_pdf("ITEM0001")
    assert zotero.posts[-1] == ("/zmc/find-pdf", {"itemKey": "ITEM0001"})
    assert bridge.find_pdf("ITEM0001")["found"] and bridge.request("GET", "/zmc/ping")["ok"]


def test_highlight_flow(zotero, pdf):
    r = bridge.highlight_quote("ITEM0001", "the main barrier to electric vehicle adoption", "supports slide 3",
                               "#FF6666", zot=FakeZot(pdf))
    assert r["ok"] and r["written"] and r["annotation_key"] == "ANNO0001" and r["attachment_key"] == "ATT00001"
    assert r["page"] == "1" and r["match"] == "exact" and r["lines"] == 2
    path, body = zotero.posts[-1]
    a = body["annotation"]
    assert path == "/zmc/annotate" and body["attachmentKey"] == "ATT00001"
    assert a["type"] == "highlight" and a["color"] == "#ff6666" and a["comment"] == "supports slide 3"
    assert a["position"]["pageIndex"] == 0 and len(a["position"]["rects"]) == 2
    assert all(842 - 130 < y < 842 - 80 for rect in a["position"]["rects"] for y in rect[1::2])


def test_highlight_not_found_writes_nothing(zotero, pdf):
    r = bridge.highlight_quote("ITEM0001", "Range anxiety is no longer a barrier for buyers", zot=FakeZot(pdf))
    assert not r["ok"] and r["written"] is False and r["candidates"]
    assert all(p != "/zmc/annotate" for p, _ in zotero.posts)


def test_highlight_errors_are_clear(zotero, pdf, monkeypatch):
    assert "#RRGGBB" in bridge.highlight_quote("ITEM0001", "anything", color="yellow")["error"]
    monkeypatch.setenv("ZMC_BRIDGE_TOKEN", "wrong")
    assert "Token 不匹配" in bridge.highlight_quote("ITEM0001", "Range anxiety", zot=FakeZot(pdf))["error"]
    zotero.installed = False
    monkeypatch.setenv("ZMC_BRIDGE_TOKEN", TOKEN)
    assert "未安装" in bridge.highlight_quote("ITEM0001", "Range anxiety", zot=FakeZot(pdf))["error"]


def test_no_pdf_attachment(zotero):
    class NoPdf(FakeZot):
        def children(self, key):
            return []
    r = bridge.highlight_quote("ITEM0001", "Range anxiety remains", zot=NoPdf(""))
    assert not r["ok"] and "zotero_find_pdf" in r["error"]


def test_tools_register_without_zotero(monkeypatch):
    """Registration must not touch Zotero, and the tools return errors instead of raising when it is down."""
    from fastmcp import FastMCP
    monkeypatch.setenv("ZMC_ZOTERO_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("ZMC_BRIDGE_TOKEN", TOKEN)
    mcp = FastMCP("t")
    bridge.register(mcp)
    names = sorted(t.name for t in asyncio.run(mcp.list_tools()))
    assert names == ["zotero_find_pdf", "zotero_highlight_quote"]
    assert "Zotero 未运行" in bridge.find_pdf("ITEM0001")["error"]
