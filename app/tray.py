"""System tray (Windows) / menu bar (macOS) icon."""
import threading
import time

import pystray

from .icons import make_icon

LABEL = {"ok": "在线", "warn": "部分异常", "bad": "离线", "idle": "已停止"}


def run_tray(services, panel, on_quit):
    icons = {k: make_icon(k, 64) for k in LABEL}

    def bg(fn):
        return lambda icon, item: threading.Thread(target=fn, daemon=True).start()

    def quit_(icon, item):
        icon.visible = False
        icon.stop()
        on_quit()

    menu = pystray.Menu(
        pystray.MenuItem("打开面板", lambda i, it: panel.open(), default=True),
        pystray.MenuItem("启动 / 重启", bg(services.start)),
        pystray.MenuItem("停止", bg(services.stop)),
        pystray.MenuItem("授权模式 15 分钟", bg(lambda: services.enter_auth_mode(15))),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出（停止服务）", quit_),
    )
    icon = pystray.Icon("ZoteroMCP", icons["idle"], "Zotero MCP", menu)

    def updater():
        last = None
        while True:
            try:
                lv = services.status().get("level", "idle")
                if lv != last:
                    icon.icon = icons[lv]
                    icon.title = f"Zotero MCP - {LABEL[lv]}"
                    if last == "ok" and lv in ("warn", "bad") and getattr(icon, "HAS_NOTIFICATION", False):
                        try:
                            icon.notify("服务出现异常，正在自动恢复。", "Zotero MCP")
                        except Exception:
                            pass
                    last = lv
            except Exception:
                pass
            time.sleep(10)

    def setup(ic):
        ic.visible = True
        threading.Thread(target=updater, daemon=True).start()

    icon.run(setup=setup)
