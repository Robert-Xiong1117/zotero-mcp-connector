import os
import sys
from pathlib import Path

from . import APP_NAME

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"


def config_dir() -> Path:
    if os.environ.get("ZMC_CONFIG_DIR"):          # tests / portable override
        d = Path(os.environ["ZMC_CONFIG_DIR"])
        d.mkdir(parents=True, exist_ok=True)
        return d
    if IS_WIN:
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif IS_MAC:
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def logs_dir() -> Path:
    d = config_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def bin_dir() -> Path:
    d = config_dir() / "bin"
    d.mkdir(parents=True, exist_ok=True)
    return d


def oauth_db_path() -> Path:
    """Same location zotero-mcp-lite uses (platformdirs user_data_dir('zotero-mcp'))."""
    if os.environ.get("ZMC_OAUTH_DB"):            # tests only: platformdirs ignores env vars on Windows
        return Path(os.environ["ZMC_OAUTH_DB"])
    try:
        from platformdirs import user_data_dir
        return Path(user_data_dir("zotero-mcp")) / "oauth.sqlite"
    except ImportError:
        return Path.home() / ".zotero-mcp" / "oauth.sqlite"


def self_command() -> list:
    """Command that re-invokes this application (frozen exe or python -m app)."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "app"]


def restrict_permissions(path: Path) -> None:
    try:
        if IS_WIN:
            import subprocess
            user = os.environ.get("USERNAME", "")
            if user:
                subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"],
                               capture_output=True, creationflags=0x08000000)
        else:
            os.chmod(path, 0o600)
    except Exception:
        pass
