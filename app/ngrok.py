"""Download, configure and run the ngrok agent (not redistributed; fetched from ngrok's official CDN)."""
import io
import os
import platform
import stat
import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path

from .config import Config
from .paths import IS_MAC, IS_WIN, bin_dir, config_dir, logs_dir, restrict_permissions

DOWNLOADS = {
    ("win", "amd64"): "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip",
    ("win", "arm64"): "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-arm64.zip",
    ("mac", "arm64"): "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-darwin-arm64.zip",
    ("mac", "amd64"): "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-darwin-amd64.zip",
    ("linux", "amd64"): "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.zip",
}


def _platform_key():
    osname = "win" if IS_WIN else "mac" if IS_MAC else "linux"
    m = platform.machine().lower()
    arch = "arm64" if m in ("arm64", "aarch64") else "amd64"
    return osname, arch


def exe_path() -> Path:
    return bin_dir() / ("ngrok.exe" if IS_WIN else "ngrok")


def ensure_installed(progress=None) -> Path:
    exe = exe_path()
    if exe.exists():
        return exe
    url = DOWNLOADS[_platform_key()]
    if progress:
        progress(f"正在下载 ngrok：{url}")
    opener = urllib.request.build_opener()
    with opener.open(url, timeout=120) as r:
        data = r.read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        name = next(n for n in z.namelist() if n.lower().startswith("ngrok"))
        exe.write_bytes(z.read(name))
    if not IS_WIN:
        exe.chmod(exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return exe


def update() -> str:
    exe = ensure_installed()
    r = subprocess.run([str(exe), "update"], capture_output=True, text=True, timeout=180,
                       creationflags=0x08000000 if IS_WIN else 0)
    return (r.stdout + r.stderr).strip()


def version() -> str:
    try:
        r = subprocess.run([str(exe_path()), "version"], capture_output=True, text=True, timeout=20,
                           creationflags=0x08000000 if IS_WIN else 0)
        return r.stdout.strip()
    except Exception:
        return ""


def policy_path() -> Path:
    return config_dir() / "ngrok-policy.yml"


def write_policy(cfg: Config) -> Path:
    allow = list(cfg.allow_cidrs)
    if cfg.auth_mode_ip and cfg.auth_mode_until > time.time():
        allow.append(f"{cfg.auth_mode_ip}/32")
    allow_yaml = "\n".join(f"            - {c}" for c in allow)
    expr = " || ".join(f"req.url.path.startsWith('{p}')" for p in cfg.login_paths)
    yaml = (
        "on_http_request:\n"
        "  - actions:\n"
        "      - type: restrict-ips\n"
        "        config:\n"
        "          enforce: true\n"
        "          allow:\n"
        f"{allow_yaml}\n"
        "  - expressions:\n"
        f"      - \"{expr}\"\n"
        "    actions:\n"
        "      - type: basic-auth\n"
        "        config:\n"
        "          realm: \"zotero-mcp\"\n"
        "          credentials:\n"
        f"            - \"{cfg.basic_user}:{cfg.basic_password}\"\n"
    )
    p = policy_path()
    p.write_text(yaml, encoding="ascii")
    restrict_permissions(p)
    return p


def start(cfg: Config) -> subprocess.Popen:
    exe = ensure_installed()
    policy = write_policy(cfg)
    env = dict(os.environ)
    env["NGROK_AUTHTOKEN"] = cfg.ngrok_authtoken
    log = logs_dir() / "ngrok.log"
    args = [str(exe), "http", f"127.0.0.1:{cfg.port}", "--url", cfg.public_url,
            "--traffic-policy-file", str(policy), "--log", str(log), "--log-format", "logfmt"]
    kw = {}
    if IS_WIN:
        kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    else:
        kw["start_new_session"] = True
    return subprocess.Popen(args, env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
