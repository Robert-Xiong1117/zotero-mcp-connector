import sys


def _serve_mcp(argv):
    """Child-process mode: run the bundled zotero-mcp-lite CLI."""
    import os
    if sys.stdout is None or sys.stderr is None:  # windowed build: no console handles
        from .paths import logs_dir
        f = open(logs_dir() / "server.log", "a", buffering=1, encoding="utf-8")
        sys.stdout = sys.stdout or f
        sys.stderr = sys.stderr or f
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    from zotero_mcp.cli import main as zmain
    sys.argv = ["zotero-mcp"] + argv
    zmain()


def _manager(argv):
    import logging
    import os
    import socket
    import threading
    import webbrowser

    from . import autostart
    from . import config as cfgmod
    from .paths import config_dir, logs_dir
    from .services import Services
    from .web import Panel

    background = "--background" in argv
    url_file = config_dir() / "panel.url"

    # single instance: a second launch just opens the running instance's panel
    lock = socket.socket()
    try:
        lock.bind(("127.0.0.1", 47809))
    except OSError:
        if url_file.exists() and not background:
            webbrowser.open(url_file.read_text().strip())
        return

    logging.basicConfig(filename=str(logs_dir() / "manager.log"), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    services = Services()
    panel = Panel(services)
    panel.serve()
    url_file.write_text(panel.url)

    cfg = cfgmod.load()
    if cfg.configured:
        autostart.launch_zotero_if_needed()
        if not cfg.paused:
            threading.Thread(target=services.start, daemon=True).start()
    if not cfg.configured or not background:
        panel.open()
    services.watchdog(60)

    def on_quit():
        services.shutdown()
        try:
            url_file.unlink()
        except Exception:
            pass
        os._exit(0)

    if "--no-tray" in argv:
        threading.Event().wait()
    else:
        from .tray import run_tray
        run_tray(services, panel, on_quit)


def main():
    import multiprocessing
    multiprocessing.freeze_support()
    argv = sys.argv[1:]
    if argv and argv[0] == "serve-mcp":
        _serve_mcp(argv[1:])
    elif argv and argv[0] == "version":
        from . import __version__
        print(__version__)
    else:
        _manager(argv)


if __name__ == "__main__":
    main()
