"""Zotero bridge plugin: token check and endpoint behaviour, run in node against a fake Zotero."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node not installed")


def run(pref_token, client_token):
    out = subprocess.run(["node", str(ROOT / "tests" / "plugin_harness.js"), pref_token, client_token],
                         capture_output=True, text=True, timeout=30, check=True).stdout
    return json.loads(out)


def test_token_required_on_every_endpoint():
    r = run("s3cret-token", "s3cret-token")
    assert r["endpoints"] == ["/zmc/ping", "/zmc/annotate", "/zmc/find-pdf"]
    assert r["ping_ok"] == {"status": 200, "body": {"ok": True, "version": "9.9.9", "zotero": "7.0-test"}}
    assert r["ping_ok_headers_map"]["status"] == 200          # Zotero 7 passes a Headers object
    for k in ("ping_no_token", "ping_bad", "annotate_bad", "find_bad"):
        assert r[k]["status"] == 403, k
    assert r["after_shutdown"] == []


def test_empty_pref_rejects_everything():
    r = run("", "")
    assert r["ping_ok"]["status"] == 403 and r["annotate_ok"]["status"] == 403 and not r["saved"]


def test_annotate_and_find_pdf():
    r = run("tok", "tok")
    assert r["annotate_ok"] == {"status": 200, "body": {"ok": True, "key": "NEWANNO1", "attachmentKey": "ATTKEY01"}}
    (s,) = r["saved"]
    assert s["attachment"] == "ATTKEY01"
    assert s["json"]["color"] == "#ff0000" and s["json"]["pageLabel"] == "1"
    assert s["json"]["position"] == {"pageIndex": 0, "rects": [[1, 2, 3, 4]]}
    assert r["annotate_missing_att"]["status"] == 404
    assert r["annotate_no_rects"]["status"] == 400
    assert r["find_ok"]["body"]["attachmentKey"] == "PDFKEY01"


def test_plugin_version_matches_app():
    from app import __version__
    manifest = json.loads((ROOT / "zotero-plugin" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == __version__
    spec = (ROOT / "packaging" / "zotero_mcp.spec").read_text(encoding="utf-8")
    assert f'"CFBundleShortVersionString": "{__version__}"' in spec
    assert '"app.bridge"' in spec and '"app.pdfquote"' in spec
