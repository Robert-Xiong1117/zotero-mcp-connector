"""Start-at-login: HKCU Run key on Windows, LaunchAgent on macOS. No admin rights needed."""
import plistlib
import subprocess
from pathlib import Path

from .paths import IS_MAC, IS_WIN, self_command

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE = "ZoteroMCP"
LABEL = "com.robertxiong.zoteromcp"


def _plist() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _command() -> list:
    cmd = self_command()
    # Inside a .app bundle, launch through `open` so macOS treats it as the app.
    if IS_MAC and ".app/Contents/MacOS/" in cmd[0]:
        app = cmd[0].split(".app/")[0] + ".app"
        return ["/usr/bin/open", "-g", app, "--args", "--background"]
    return cmd + ["--background"]


def enable() -> None:
    cmd = _command()
    if IS_WIN:
        import winreg
        quoted = " ".join(f'"{c}"' if " " in c else c for c in cmd)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, VALUE, 0, winreg.REG_SZ, quoted)
    elif IS_MAC:
        p = _plist()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(plistlib.dumps({"Label": LABEL, "ProgramArguments": cmd, "RunAtLoad": True}))


def disable() -> None:
    if IS_WIN:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, VALUE)
        except FileNotFoundError:
            pass
    elif IS_MAC:
        _plist().unlink(missing_ok=True)


def is_enabled() -> bool:
    if IS_WIN:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
                winreg.QueryValueEx(k, VALUE)
                return True
        except FileNotFoundError:
            return False
    if IS_MAC:
        return _plist().exists()
    return False


def launch_zotero_if_needed() -> None:
    try:
        import psutil
        if any((p.info.get("name") or "").lower().startswith("zotero") for p in psutil.process_iter(["name"])):
            return
    except Exception:
        pass
    if IS_WIN:
        for exe in (Path(r"C:\Program Files\Zotero\zotero.exe"), Path(r"C:\Program Files (x86)\Zotero\zotero.exe")):
            if exe.exists():
                subprocess.Popen([str(exe)], creationflags=0x00000008)  # DETACHED_PROCESS
                return
    elif IS_MAC and Path("/Applications/Zotero.app").exists():
        subprocess.Popen(["/usr/bin/open", "-g", "-a", "Zotero"])
