"""Zotero must actually get started: at login, and again if it is closed while the connector runs.

Every tool needs Zotero's local API on 23119. If Zotero is not running, the connector still answers
but every call fails with "connection refused" (WinError 10061), which is what the PowerPoint add-in hit.
"""
from types import SimpleNamespace

from app import autostart


class _Proc:
    def __init__(self, name):
        self.info = {"name": name}


def _fake_psutil(monkeypatch, names):
    import psutil
    monkeypatch.setattr(psutil, "process_iter", lambda attrs=None: [_Proc(n) for n in names])


def test_connector_itself_is_not_mistaken_for_zotero(monkeypatch):
    # ZoteroMCP.exe starts with "zotero"; it used to count as "Zotero is running", so Zotero never got launched.
    _fake_psutil(monkeypatch, ["ZoteroMCP.exe", "ngrok.exe", "explorer.exe"])
    assert autostart.zotero_running() is False


def test_real_zotero_process_is_recognised(monkeypatch):
    for name in ("zotero.exe", "Zotero.exe", "zotero"):
        _fake_psutil(monkeypatch, ["ZoteroMCP.exe", name])
        assert autostart.zotero_running() is True


def test_launch_skips_when_zotero_is_already_running(monkeypatch):
    _fake_psutil(monkeypatch, ["zotero.exe"])
    started = []
    monkeypatch.setattr(autostart.subprocess, "Popen", lambda *a, **k: started.append(a))
    assert autostart.launch_zotero_if_needed() is False
    assert started == []


def test_launch_starts_zotero_when_only_the_connector_runs(monkeypatch, tmp_path):
    _fake_psutil(monkeypatch, ["ZoteroMCP.exe"])
    exe = tmp_path / "zotero.exe"; exe.write_text("")
    monkeypatch.setattr(autostart, "IS_WIN", True)
    monkeypatch.setattr(autostart, "IS_MAC", False)
    monkeypatch.setattr(autostart, "ZOTERO_WIN_PATHS", (exe,))
    started = []
    monkeypatch.setattr(autostart.subprocess, "Popen", lambda args, **k: started.append(args))
    assert autostart.launch_zotero_if_needed() is True
    assert started == [[str(exe)]]


def test_watchdog_relaunches_closed_zotero_at_most_every_ten_minutes(monkeypatch):
    from app import services as svc
    s = svc.Services()
    launched = []
    monkeypatch.setattr(svc.autostart, "launch_zotero_if_needed", lambda: launched.append(1) or True)
    now = [1_000_000.0]
    monkeypatch.setattr(svc.time, "time", lambda: now[0])
    s.relaunch_zotero_if_down({"zotero": 0})
    s.relaunch_zotero_if_down({"zotero": 0})          # one minute later: no second launch
    assert len(launched) == 1
    now[0] += 601
    s.relaunch_zotero_if_down({"zotero": 0})
    assert len(launched) == 2
    s.relaunch_zotero_if_down({"zotero": 200})        # up: nothing to do
    assert len(launched) == 2
    assert any("Zotero" in e for e in s.events)
