"""Clients that skip the session handshake (the Claude PowerPoint add-in does) must still get answers.

In stateful mode the MCP library rejects any POST without an `Mcp-Session-Id` header with
HTTP 400 "Bad Request: Missing session ID". The connector serves stateless HTTP so every request
stands on its own. This test boots a server with exactly the run options app/serve.py uses.
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

BOOT = r"""
import sys
from fastmcp import FastMCP
from app.serve import HTTP_RUN_OPTIONS
mcp = FastMCP("t")

@mcp.tool
def ping() -> str:
    return "pong"

opts = dict(HTTP_RUN_OPTIONS)
if sys.argv[2] == "stateful":
    opts["stateless_http"] = False
mcp.run(transport="streamable-http", host="127.0.0.1", port=int(sys.argv[1]), show_banner=False, **opts)
"""

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    return port


def _post(port, body):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/mcp", data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                 "MCP-Protocol-Version": "2025-06-18"})          # no Mcp-Session-Id, like the add-in
    try:
        r = OPENER.open(req, timeout=10)
        return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def _call_without_session(mode):
    port = _free_port()
    p = subprocess.Popen([sys.executable, "-c", BOOT, str(port), mode], cwd=ROOT,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=1).close(); break
            except OSError:
                time.sleep(0.5)
        return _post(port, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                            "params": {"name": "ping", "arguments": {}}})
    finally:
        p.kill(); p.wait()


def test_stateful_mode_reproduces_missing_session_id():
    code, body = _call_without_session("stateful")
    assert code == 400 and "Missing session ID" in body


def test_connector_answers_calls_without_session_id():
    code, body = _call_without_session("connector")
    assert code == 200, body
    assert "pong" in body


def test_real_connector_is_stateless_and_still_behind_oauth(tmp_path):
    """The production child (serve-connector): OAuth still guards POST, GET is 405 in stateless
    mode, and the health check the watchdog uses still reports the server as up."""
    from app.services import http_code, mcp_server_up
    port = _free_port()
    env = dict(os.environ, HOME=str(tmp_path), XDG_CONFIG_HOME=str(tmp_path / "c"), XDG_DATA_HOME=str(tmp_path / "d"),
               ZOTERO_MCP_ADMIN_PASSWORD="x" * 40, ZOTERO_MCP_PUBLIC_URL="https://x.ngrok-free.dev",
               ZMC_TEST_DATA=str(tmp_path / "data"))
    boot = ("import os, sys, platformdirs; platformdirs.user_data_dir = lambda *a, **k: os.environ['ZMC_TEST_DATA']; "
            "sys.argv = ['app'] + sys.argv[1:]; from app.__main__ import main; main()")
    log = tmp_path / "srv.log"
    p = subprocess.Popen([sys.executable, "-c", boot, "serve-connector", str(port)], cwd=ROOT, env=env,
                         stdout=open(log, "w"), stderr=subprocess.STDOUT)
    try:
        assert any(mcp_server_up(port, 2) or time.sleep(0.5) for _ in range(90)), log.read_text()[-2000:]
        code, _ = _post(port, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert code == 401                                   # no token: still rejected, OAuth untouched
        assert http_code(f"http://127.0.0.1:{port}/mcp", 2) == 405   # why the old GET probe had to go
        assert "HTTP: stateless" in log.read_text()
    finally:
        p.kill(); p.wait()
