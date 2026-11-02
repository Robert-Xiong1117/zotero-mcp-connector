import asyncio
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

PORT = 18791
URL = f"http://127.0.0.1:{PORT}/ai4paper/mcp"


def _wait(url, ok=lambda c: c != 0, tries=60):
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(tries):
        try:
            op.open(url, timeout=2); return 200
        except urllib.error.HTTPError as e:
            if ok(e.code):
                return e.code
        except Exception:
            pass
        time.sleep(0.5)
    return 0


@pytest.fixture(scope="module")
def backend():
    p = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(__file__), "mock_ai4paper.py"), str(PORT)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert _wait(URL)
    yield
    p.kill()


@pytest.fixture(autouse=True)
def no_proxy(monkeypatch):
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")


def test_probe_finds_bearer_and_tools(backend):
    from app.ai4paper import probe
    r = probe(URL, "a4p-mcp-test")
    assert r["ok"] and r["scheme"] == "bearer"
    assert "zotero_search_items" in r["tools"]
    assert probe(URL, "wrong-token", timeout=5)["ok"] is False


def _parent(monkeypatch, allowed, url=URL):
    from fastmcp import FastMCP
    from app.ai4paper import mount_from_env
    monkeypatch.setenv("ZMC_AI4PAPER_TOKEN", "a4p-mcp-test")
    monkeypatch.setenv("ZMC_AI4PAPER_URL", url)
    monkeypatch.setenv("ZMC_AI4PAPER_SCHEME", "bearer")
    monkeypatch.setenv("ZMC_AI4PAPER_TOOLS", ",".join(allowed))
    parent = FastMCP("parent")

    @parent.tool
    def zotero_get_recent() -> str:
        return "recent"

    assert mount_from_env(parent)
    return parent


def test_mount_allowlist_and_namespace(backend, monkeypatch):
    from fastmcp import Client
    parent = _parent(monkeypatch, ["zotero_search_items", "zotero_add_tag"])

    async def run():
        async with Client(parent) as c:
            names = {t.name for t in await c.list_tools()}
            res = await c.call_tool("ai4paper_zotero_search_items", {"query": "PLS"})
            blocked = None
            try:
                await c.call_tool("ai4paper_zotero_delete_tags_from_library", {"tag": "x"})
            except Exception as e:
                blocked = e
            return names, res, blocked

    names, res, blocked = asyncio.run(run())
    assert names == {"zotero_get_recent", "ai4paper_zotero_search_items", "ai4paper_zotero_add_tag"}
    assert "found:PLS" in str(res.content)
    assert blocked is not None, "hidden tool must not be callable"


def test_backend_down_does_not_break_main_tools(monkeypatch):
    from fastmcp import Client
    parent = _parent(monkeypatch, ["zotero_search_items"], url="http://127.0.0.1:1/ai4paper/mcp")

    async def run():
        async with Client(parent) as c:
            return {t.name for t in await c.list_tools()}

    assert "zotero_get_recent" in asyncio.run(run())


def test_connector_child_starts_with_proxy(backend, tmp_path):
    env = dict(os.environ, HOME=str(tmp_path), XDG_CONFIG_HOME=str(tmp_path / "c"), XDG_DATA_HOME=str(tmp_path / "d"),
               ZOTERO_MCP_ADMIN_PASSWORD="x" * 40, ZOTERO_MCP_PUBLIC_URL="https://x.ngrok-free.dev",
               ZMC_AI4PAPER_TOKEN="a4p-mcp-test", ZMC_AI4PAPER_URL=URL, ZMC_AI4PAPER_SCHEME="bearer",
               ZMC_AI4PAPER_TOOLS="zotero_search_items", NO_PROXY="127.0.0.1")
    log = tmp_path / "srv.log"
    p = subprocess.Popen([sys.executable, "-m", "app", "serve-connector", "18792"], env=env,
                         stdout=open(log, "w"), stderr=subprocess.STDOUT)
    try:
        assert _wait("http://127.0.0.1:18792/mcp", ok=lambda c: c == 401) == 401
        assert "AI4Paper proxy: mounted" in log.read_text()
    finally:
        p.kill()
