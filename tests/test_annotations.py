"""Annotations via Zotero's local API, against a mock that behaves like Zotero 10's (incl. its quirks)."""
import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from app import annotations


def _item(key, **data):
    return {"key": key, "data": {"key": key, **data}}


ITEMS = [
    _item("PAPER001", itemType="journalArticle", title="Paper One"),
    _item("PAPER002", itemType="journalArticle", title="Paper Two"),
    _item("ATT00001", itemType="attachment", parentItem="PAPER001", contentType="application/pdf", filename="one.pdf"),
    _item("ATT00002", itemType="attachment", parentItem="PAPER002", contentType="application/pdf", filename="two.pdf"),
    _item("NOTE0001", itemType="note", parentItem="PAPER001", note="<p>n</p>"),
]
# 130 annotations on paper one (forces paging), two on paper two
for i in range(130):
    ITEMS.append(_item(f"A1{i:06d}", itemType="annotation", parentItem="ATT00001", annotationType="highlight",
                       annotationText=f"filler {i}" if i != 120 else "Trust drives adoption", annotationComment="",
                       annotationColor="#ffd400", annotationPageLabel=str(i), annotationSortIndex=f"00000|{i:06d}|00000"))
ITEMS += [
    _item("A2000001", itemType="annotation", parentItem="ATT00002", annotationType="underline",
          annotationText="second", annotationComment="about TRUST too", annotationColor="#ff6666",
          annotationPageLabel="7", annotationSortIndex="00001|000010|00100"),
    _item("A2000000", itemType="annotation", parentItem="ATT00002", annotationType="highlight",
          annotationText="first", annotationComment="", annotationColor="#ffd400",
          annotationPageLabel="3", annotationSortIndex="00000|000001|00100"),
]
BY_KEY = {it["key"]: it for it in ITEMS}


class MockLocalApi:
    def __init__(self):
        self.requests = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, obj, total=None):
                b = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                if total is not None:
                    self.send_header("Total-Results", str(total))
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                u = urlparse(self.path)
                q = {k: v[0] for k, v in parse_qs(u.query).items()}
                outer.requests.append((u.path, q))
                parts = u.path.split("/")[4:]          # after /api/users/0
                if parts[0] != "items":
                    return self._send(404, "nope")
                if len(parts) == 2:
                    it = BY_KEY.get(parts[1])
                    return self._send(200, it) if it else self._send(404, "Not found")
                rows = ITEMS if len(parts) == 1 else [it for it in ITEMS if it["data"].get("parentItem") == parts[1]]
                if q.get("itemType"):
                    rows = [it for it in rows if it["data"]["itemType"] == q["itemType"]]
                if q.get("q"):                          # like Zotero: loose match, here text/comment/attachment name
                    needle = q["q"].lower()
                    rows = [it for it in rows if needle in json.dumps(it["data"]).lower() or "filler" in
                            (it["data"].get("annotationText") or "")]          # extra candidates, as with full text
                # NB: real local API ignores itemKey — so does the mock
                start, limit = int(q.get("start", 0)), int(q.get("limit", 25))
                return self._send(200, rows[start:start + limit], total=len(rows))

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()


@pytest.fixture
def api(monkeypatch):
    m = MockLocalApi()
    monkeypatch.setenv("ZMC_ZOTERO_URL", m.url)
    yield m
    m.httpd.shutdown()


def test_search_matches_text_or_comment_with_parent_info(api):
    r = annotations.LocalApiAnnotations().search_annotations("trust")
    assert [(a.parent_key, a.parent_title, a.text, a.comment, a.page_label, a.type) for a in r] == [
        ("PAPER001", "Paper One", "Trust drives adoption", "", "120", "highlight"),
        ("PAPER002", "Paper Two", "second", "about TRUST too", "7", "underline"),
    ]
    assert r[0].attachment_name == "one.pdf"
    assert not any("itemKey" in q for _, q in api.requests)          # never relies on the ignored filter


def test_search_limit_and_paging(api):
    assert len(annotations.LocalApiAnnotations().search_annotations("filler", limit=5)) == 5
    r = annotations.LocalApiAnnotations().search_annotations("filler", limit=500)
    assert len(r) == 129                                             # all pages read, 'Trust' one excluded


def test_item_annotations_sorted_and_attachment_key(api):
    db = annotations.LocalApiAnnotations()
    two = db.get_annotations_for_item("PAPER002")
    assert [a.text for a in two] == ["first", "second"] and two[0].attachment_name == "two.pdf"
    assert len(db.get_annotations_for_item("PAPER001")) == 130         # beyond one page
    assert [a.text for a in db.get_annotations_for_item("ATT00002")] == ["first", "second"]


def test_install_routes_lite_tools_through_local_api(api, monkeypatch):
    from fastmcp import Client
    from zotero_mcp import local_db
    monkeypatch.setattr(local_db, "get_local_db", local_db.get_local_db)   # restored after the test
    annotations.install()
    from zotero_mcp.server import mcp

    async def call():
        async with Client(mcp) as c:
            r = await c.call_tool("zotero_search_annotations", {"query": "TRUST"})
            return r.content[0].text
    text = asyncio.run(call())
    assert "## Paper One" in text and '"Trust drives adoption"' in text and "-> Comment: about TRUST too" in text


def test_zotero_offline_is_an_error_not_a_crash(monkeypatch):
    monkeypatch.setenv("ZMC_ZOTERO_URL", "http://127.0.0.1:9")
    with pytest.raises(OSError):
        annotations.LocalApiAnnotations().search_annotations("x")
