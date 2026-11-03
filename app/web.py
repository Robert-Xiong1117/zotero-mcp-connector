"""Local control panel served on 127.0.0.1 only, protected by a per-launch token."""
import json
import secrets
import socket
import subprocess
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import __version__, autostart, backup, ngrok
from . import config as cfgmod
from .paths import IS_MAC, IS_WIN, logs_dir
from .panel_html import PAGE

TOKEN = secrets.token_urlsafe(24)
XPI_URL = "https://github.com/Robert-Xiong1117/zotero-mcp-connector/releases/latest"


def _free_port(preferred=47811) -> int:
    for p in range(preferred, preferred + 20):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise RuntimeError("no free port")


class Panel:
    def __init__(self, services):
        self.services = services
        self.port = _free_port()
        self.httpd = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/?t={TOKEN}"

    def open(self) -> None:
        webbrowser.open(self.url)

    def serve(self) -> None:
        panel = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _ok_origin(self) -> bool:
                host = (self.headers.get("Host") or "").split(":")[0]
                return host in ("127.0.0.1", "localhost")

            def _authed(self) -> bool:
                if not self._ok_origin():
                    return False
                if self.headers.get("X-Token") == TOKEN:
                    return True
                q = parse_qs(urlparse(self.path).query)
                return q.get("t", [""])[0] == TOKEN

            def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
                if isinstance(body, (dict, list)):
                    body = json.dumps(body, ensure_ascii=False).encode("utf-8")
                elif isinstance(body, str):
                    body = body.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Frame-Options", "DENY")
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _body(self):
                n = int(self.headers.get("Content-Length") or 0)
                return self.rfile.read(n) if n else b""

            def do_GET(self):
                if not self._authed():
                    return self._send(403, "Forbidden: open the panel from the tray menu.", "text/plain; charset=utf-8")
                path = urlparse(self.path).path
                if path == "/":
                    return self._send(200, PAGE.replace("__TOKEN__", TOKEN).replace("__VERSION__", __version__),
                                      "text/html; charset=utf-8")
                if path == "/api/status":
                    st = panel.services.status()
                    st["autostart"] = autostart.is_enabled()
                    st["ngrok_version"] = ngrok.version()
                    return self._send(200, st)
                if path == "/api/ai4paper":
                    from .ai4paper import DEFAULT_TOOLS, RISKY_TOOLS, WRITE_TOOLS
                    c = cfgmod.load()
                    return self._send(200, {"enabled": c.ai4paper_enabled, "has_token": bool(c.ai4paper_token),
                                            "url": c.ai4paper_url, "scheme": c.ai4paper_scheme,
                                            "selected": cfgmod.ai4paper_tools(c), "defaults": DEFAULT_TOOLS,
                                            "write": sorted(WRITE_TOOLS), "risky": sorted(RISKY_TOOLS),
                                            "known": sorted(set(DEFAULT_TOOLS) | WRITE_TOOLS | set(c.ai4paper_tools))})
                if path == "/api/bridge":
                    c = cfgmod.load()
                    if c.configured and not c.zmc_bridge_token:
                        c.ensure_secrets()
                        cfgmod.save(c)
                    from . import bridge
                    return self._send(200, {"token": c.zmc_bridge_token, "ping": bridge.ping(c.zmc_bridge_token),
                                            "xpi": XPI_URL})
                if path == "/api/credentials":
                    c = cfgmod.load()
                    return self._send(200, {"basic_user": c.basic_user, "basic_password": c.basic_password,
                                            "admin_password": c.admin_password, "domain": c.domain})
                return self._send(404, {"error": "not found"})

            def do_POST(self):
                if not self._authed():
                    return self._send(403, {"error": "forbidden"})
                path = urlparse(self.path).path
                svc = panel.services
                try:
                    if path == "/api/import":
                        pw = self.headers.get("X-Passphrase", "")
                        backup.import_bundle(self._body(), pw)
                        threading.Thread(target=svc.start, daemon=True).start()
                        return self._send(200, {"ok": True})
                    data = json.loads(self._body() or b"{}")
                    if path == "/api/setup":
                        c = cfgmod.load()
                        if data.get("ngrok_authtoken"):
                            c.ngrok_authtoken = data["ngrok_authtoken"].strip()
                        if data.get("domain"):
                            c.domain = cfgmod.normalize_domain(data["domain"])
                        if not (c.ngrok_authtoken and c.domain):
                            return self._send(400, {"error": "请填写 ngrok Authtoken 和固定域名"})
                        c.ensure_secrets()
                        cfgmod.save(c)
                        threading.Thread(target=panel._first_start, daemon=True).start()
                        return self._send(200, {"ok": True})
                    if path == "/api/import-legacy":
                        c = cfgmod.import_legacy(data.get("folder", ""))
                        cfgmod.save(c)
                        return self._send(200, {"ok": True, "domain": c.domain,
                                                "found_password": bool(c.admin_password),
                                                "found_basic": bool(c.basic_user)})
                    if path == "/api/ai4paper-test":
                        from . import ai4paper
                        c = cfgmod.load()
                        token = (data.get("token") or "").strip() or c.ai4paper_token
                        if not token:
                            return self._send(400, {"error": "请填写 AI4Paper Token"})
                        res = ai4paper.probe(c.ai4paper_url, token)
                        if res.get("ok"):
                            c.ai4paper_token, c.ai4paper_scheme = token, res["scheme"]
                            cfgmod.save(c)
                        return self._send(200, res)
                    if path == "/api/ai4paper-save":
                        c = cfgmod.load()
                        c.ai4paper_enabled = bool(data.get("enabled"))
                        if isinstance(data.get("tools"), list):
                            c.ai4paper_tools = [t for t in data["tools"] if isinstance(t, str)]
                        if c.ai4paper_enabled and not (c.ai4paper_token and c.ai4paper_scheme):
                            return self._send(400, {"error": "请先填写 Token 并点「测试连接」"})
                        cfgmod.save(c)
                        threading.Thread(target=svc.start, daemon=True).start()
                        return self._send(200, {"ok": True})
                    if path == "/api/start":
                        threading.Thread(target=svc.start, daemon=True).start()
                        return self._send(200, {"ok": True})
                    if path == "/api/stop":
                        svc.stop()
                        return self._send(200, {"ok": True})
                    if path == "/api/auth-mode":
                        ip = svc.enter_auth_mode(int(data.get("minutes", 15)))
                        return self._send(200 if ip else 500, {"ip": ip} if ip else {"error": "无法获取本机公网 IP"})
                    if path == "/api/auth-mode-end":
                        svc.exit_auth_mode()
                        return self._send(200, {"ok": True})
                    if path == "/api/autostart":
                        (autostart.enable if data.get("enabled") else autostart.disable)()
                        return self._send(200, {"ok": True, "enabled": autostart.is_enabled()})
                    if path == "/api/ngrok-update":
                        out = ngrok.update()
                        threading.Thread(target=svc.start, daemon=True).start()
                        return self._send(200, {"output": out})
                    if path == "/api/export":
                        blob = backup.export_bundle(data.get("passphrase", ""))
                        return self._send(200, blob, "application/octet-stream",
                                          {"Content-Disposition": 'attachment; filename="zotero-mcp-backup.zmcp"'})
                    if path == "/api/open-logs":
                        d = str(logs_dir())
                        if IS_WIN:
                            subprocess.Popen(["explorer", d])
                        elif IS_MAC:
                            subprocess.Popen(["open", d])
                        return self._send(200, {"ok": True})
                    return self._send(404, {"error": "not found"})
                except ValueError as e:
                    return self._send(400, {"error": str(e)})
                except Exception as e:
                    return self._send(500, {"error": f"{type(e).__name__}: {e}"})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", self.port), H)
        threading.Thread(target=self.httpd.serve_forever, daemon=True, name="panel").start()

    def _first_start(self) -> None:
        svc = self.services
        try:
            svc.note("正在准备 ngrok…")
            ngrok.ensure_installed(svc.note)
            autostart.enable()
            if svc.start():
                svc.enter_auth_mode(30)
        except Exception as e:
            svc.note(f"首次启动失败：{e}")
