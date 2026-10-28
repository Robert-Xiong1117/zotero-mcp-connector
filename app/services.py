"""Start/stop/health-check of the MCP server and the ngrok tunnel, plus a watchdog."""
import json
import logging
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request

from . import config as cfgmod
from . import ngrok
from .paths import IS_WIN, logs_dir, self_command

log = logging.getLogger("zotero-mcp-connector")
_NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
ZOTERO_API = "http://127.0.0.1:23119/api/users/0/items?limit=1"
NGROK_API = "http://127.0.0.1:4040/api"


def http_code(url: str, timeout: float = 5.0, headers=None) -> int:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with _NOPROXY.open(req, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def http_json(url: str, timeout: float = 3.0):
    try:
        with _NOPROXY.open(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def public_ip() -> str:
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                ip = r.read().decode().strip()
                if ip.count(".") == 3:
                    return ip
        except Exception:
            continue
    return ""


class Services:
    def __init__(self):
        self.lock = threading.RLock()
        self.server = None
        self.tunnel = None
        self.last_status = {}
        self.events = []          # short history shown in the panel
        self._stop = threading.Event()

    # ---------- helpers ----------
    def note(self, msg: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.events.append(f"{stamp}  {msg}")
        self.events = self.events[-30:]
        log.info(msg)

    @staticmethod
    def _kill(proc):
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=8)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def _kill_strays(self, port: int) -> None:
        """Kill leftovers (e.g. from a crashed manager) holding our port / an orphan ngrok."""
        try:
            import psutil
            me = os.getpid()
            for p in psutil.process_iter(["pid"]):
                if p.pid in (0, 4, me):
                    continue
                try:
                    for c in p.net_connections(kind="tcp"):
                        if c.laddr and c.laddr.port == port and c.status == psutil.CONN_LISTEN:
                            p.kill()
                            break
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    continue
            for p in psutil.process_iter(["name"]):
                if (p.info.get("name") or "").lower() in ("ngrok", "ngrok.exe"):
                    p.kill()
        except Exception:
            pass

    # ---------- lifecycle ----------
    def start(self) -> bool:
        with self.lock:
            cfg = cfgmod.load()
            if not cfg.configured:
                self.note("尚未完成设置")
                return False
            cfg.paused = False
            cfgmod.save(cfg)
            self.stop(keep_paused_flag=True)
            self._kill_strays(cfg.port)

            env = dict(os.environ)
            env["ZOTERO_MCP_ADMIN_PASSWORD"] = cfg.admin_password
            env["ZOTERO_MCP_PUBLIC_URL"] = cfg.public_url
            out = open(logs_dir() / "server.log", "ab")
            kw = {"creationflags": 0x08000000} if IS_WIN else {"start_new_session": True}
            cmd = self_command() + ["serve-mcp", "serve", "--transport", "streamable-http",
                                    "--host", "127.0.0.1", "--port", str(cfg.port)]
            self.server = subprocess.Popen(cmd, env=env, stdin=subprocess.DEVNULL,
                                           stdout=out, stderr=out, **kw)
            for _ in range(90):
                if http_code(f"http://127.0.0.1:{cfg.port}/mcp", 2) == 401:
                    break
                if self.server.poll() is not None:
                    self.note("MCP 服务器启动失败，查看 logs/server.log")
                    return False
                time.sleep(1)
            else:
                self.note("MCP 服务器 90 秒内未就绪")
                return False

            try:
                self.tunnel = ngrok.start(cfg)
            except Exception as e:
                self.note(f"ngrok 启动失败：{e}")
                return False
            for _ in range(30):
                if self._tunnel_up(cfg):
                    self.note("已启动：服务器与隧道在线")
                    return True
                if self.tunnel.poll() is not None:
                    break
                time.sleep(1)
            self.note("ngrok 隧道未建立，查看 logs/ngrok.log")
            return False

    def stop(self, keep_paused_flag: bool = False) -> None:
        with self.lock:
            self._kill(self.tunnel)
            self._kill(self.server)
            self.tunnel = self.server = None
            if not keep_paused_flag:
                cfg = cfgmod.load()
                cfg.paused = True
                cfgmod.save(cfg)
                self.note("已停止（自动守护已暂停）")

    def restart_tunnel(self) -> None:
        """Re-apply the traffic policy (e.g. auth mode on/off) without touching the server."""
        with self.lock:
            cfg = cfgmod.load()
            self._kill(self.tunnel)
            self.tunnel = ngrok.start(cfg)

    # ---------- auth mode ----------
    def enter_auth_mode(self, minutes: int = 15) -> str:
        ip = public_ip()
        if not ip:
            return ""
        cfg = cfgmod.load()
        cfg.auth_mode_ip = ip
        cfg.auth_mode_until = time.time() + minutes * 60
        cfgmod.save(cfg)
        self.restart_tunnel()
        self.note(f"授权模式开启 {minutes} 分钟（临时放行 {ip}）")
        return ip

    def exit_auth_mode(self) -> None:
        cfg = cfgmod.load()
        cfg.auth_mode_ip, cfg.auth_mode_until = "", 0.0
        cfgmod.save(cfg)
        self.restart_tunnel()
        self.note("授权模式已结束，白名单只保留 Anthropic")

    # ---------- health ----------
    @staticmethod
    def _tunnel_up(cfg) -> bool:
        data = http_json(f"{NGROK_API}/tunnels")
        if not data:
            return False
        return any(t.get("public_url", "").rstrip("/") == cfg.public_url for t in data.get("tunnels", []))

    def status(self) -> dict:
        cfg = cfgmod.load()
        st = {
            "configured": cfg.configured,
            "paused": cfg.paused,
            "url": f"{cfg.public_url}/mcp" if cfg.domain else "",
            "zotero": http_code(ZOTERO_API, 3),
            "server": http_code(f"http://127.0.0.1:{cfg.port}/mcp", 3) == 401,
            "tunnel": self._tunnel_up(cfg) if cfg.configured else False,
            "auth_mode_left": max(0, int(cfg.auth_mode_until - time.time())),
            "auth_mode_ip": cfg.auth_mode_ip,
            "events": list(self.events[-10:]),
            "requests": [],
        }
        if st["tunnel"]:
            data = http_json(f"{NGROK_API}/requests/http?limit=10") or {}
            for q in data.get("requests", []):
                ip = (q.get("remote_addr") or "").split(":")[0]
                st["requests"].append({
                    "time": (q.get("start") or "")[11:19],
                    "method": (q.get("request") or {}).get("method", ""),
                    "path": ((q.get("request") or {}).get("uri", "")).split("?")[0],
                    "status": (q.get("response") or {}).get("status_code", ""),
                    "from": "Claude" if ip.startswith("160.79.") else ip,
                })
        if not cfg.configured:
            st["level"] = "idle"
        elif cfg.paused:
            st["level"] = "idle"
        elif st["zotero"] == 200 and st["server"] and st["tunnel"]:
            st["level"] = "ok"
        elif st["server"] or st["tunnel"]:
            st["level"] = "warn"
        else:
            st["level"] = "bad"
        self.last_status = st
        return st

    # ---------- watchdog ----------
    def watchdog(self, interval: int = 60) -> None:
        def loop():
            time.sleep(5)
            while not self._stop.is_set():
                try:
                    cfg = cfgmod.load()
                    if cfg.auth_mode_until and cfg.auth_mode_until < time.time():
                        self.exit_auth_mode()
                    if cfg.configured and not cfg.paused:
                        st = self.status()
                        if st["zotero"] != 200:
                            pass  # wait for Zotero; nothing useful to restart
                        elif not (st["server"] and st["tunnel"]):
                            self.note("检测到异常，自动重启")
                            self.start()
                except Exception as e:
                    log.exception("watchdog: %s", e)
                self._stop.wait(interval)
        threading.Thread(target=loop, daemon=True, name="watchdog").start()

    def shutdown(self) -> None:
        self._stop.set()
        with self.lock:
            self._kill(self.tunnel)
            self._kill(self.server)
