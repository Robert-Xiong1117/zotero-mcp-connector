"""Local stdio mode (DeepSeek Harness etc.): same tools as the tunnel server, tokens from this app's config."""
import asyncio
import os
import sys
from pathlib import Path

from test_bridge import TOKEN, MockZotero

ROOT = Path(__file__).resolve().parent.parent


def _client(extra_env):
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport
    env = {k: v for k, v in os.environ.items() if not k.startswith("ZMC_BRIDGE")}
    env.update(extra_env)
    return Client(StdioTransport(command=sys.executable, args=["-m", "app", "serve-stdio"], env=env, cwd=str(ROOT)),
                  timeout=60)


def test_stdio_exposes_all_tools_and_uses_config_token(monkeypatch):
    from app import config as c
    cfg = c.Config(); cfg.ensure_secrets(); cfg.zmc_bridge_token = TOKEN; c.save(cfg)
    z = MockZotero()
    try:
        async def run():
            async with _client({"ZMC_ZOTERO_URL": z.url}) as cl:
                names = {t.name for t in await cl.list_tools()}
                r = await cl.call_tool("zotero_find_pdf", {"item_key": "ITEM0001"})
                return names, r.data if r.data is not None else r.structured_content
        names, found = asyncio.run(run())
    finally:
        z.httpd.shutdown()
    assert {"zotero_search_items", "zotero_get_item_fulltext", "zotero_search_annotations", "zotero_create_note",
            "zotero_highlight_quote", "zotero_find_pdf"} <= names
    assert found["ok"] and found["attachment_key"] == "PDF00001"          # plugin accepted the token from config
    assert z.posts and z.posts[-1][0] == "/zmc/find-pdf"


def test_stdio_without_zotero_reports_errors_cleanly():
    from app import config as c
    cfg = c.Config(); cfg.ensure_secrets(); c.save(cfg)

    async def run():
        async with _client({"ZMC_ZOTERO_URL": "http://127.0.0.1:9"}) as cl:
            r = await cl.call_tool("zotero_find_pdf", {"item_key": "ITEM0001"}, raise_on_error=False)
            return r.data if r.data is not None else r.structured_content
    out = asyncio.run(run())
    assert out["ok"] is False and "Zotero 未运行" in out["error"]


def test_panel_gives_ready_to_paste_client_config():
    import json
    import urllib.request
    import yaml
    from app.web import TOKEN, Panel
    panel = Panel(None); panel.serve()
    try:
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req = urllib.request.Request(f"http://127.0.0.1:{panel.port}/api/local-client", headers={"X-Token": TOKEN})
        r = json.loads(op.open(req, timeout=5).read())
    finally:
        panel.httpd.shutdown()
    assert r["args"][-1] == "serve-stdio"
    (entry,) = yaml.safe_load(r["deepseek_yml"])[0]["insert"]
    assert entry["name"] == "@deepseek-ai/dsh-mcp-client"
    assert entry["config"]["transport"] == "stdio" and entry["config"]["command"] == r["command"]
    assert entry["config"]["args"] == r["args"]
    assert entry["id"] == entry["config"]["serverName"] == "zoteromcp"      # must not clash with an existing "zotero" server
    assert json.loads(r["json"])["mcpServers"]["zoteromcp"]["args"] == r["args"]
