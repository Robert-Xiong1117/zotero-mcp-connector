import json
import secrets
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .paths import config_dir, restrict_permissions

ANTHROPIC_CIDR = "160.79.104.0/21"


@dataclass
class Config:
    ngrok_authtoken: str = ""
    domain: str = ""                      # e.g. foo.ngrok-free.dev
    admin_password: str = ""              # 2nd factor: zotero-mcp-lite login page
    basic_user: str = ""                  # 1st factor: ngrok basic-auth on login paths
    basic_password: str = ""
    port: int = 8000
    allow_cidrs: list = field(default_factory=lambda: [ANTHROPIC_CIDR])
    login_paths: list = field(default_factory=lambda: ["/authorize"])
    auth_mode_until: float = 0.0          # epoch seconds; personal IP allowed until then
    auth_mode_ip: str = ""
    paused: bool = False
    autostart: bool = True
    ai4paper_enabled: bool = False
    ai4paper_token: str = ""
    ai4paper_url: str = "http://127.0.0.1:23119/ai4paper/mcp"
    ai4paper_scheme: str = ""             # resolved by probe: bearer | x-api-key | query
    ai4paper_tools: list = field(default_factory=list)   # empty = defaults

    @property
    def public_url(self) -> str:
        return f"https://{self.domain}" if self.domain else ""

    @property
    def configured(self) -> bool:
        return bool(self.ngrok_authtoken and self.domain and self.admin_password
                    and self.basic_user and self.basic_password)

    def ensure_secrets(self) -> None:
        if not self.admin_password:
            self.admin_password = secrets.token_urlsafe(32)
        if not self.basic_user:
            self.basic_user = "zotero-" + secrets.token_hex(3)
        if not self.basic_password:
            self.basic_password = secrets.token_urlsafe(24)


def ai4paper_tools(cfg: "Config") -> list:
    from .ai4paper import DEFAULT_TOOLS
    return list(cfg.ai4paper_tools) if cfg.ai4paper_tools else list(DEFAULT_TOOLS)


def config_path() -> Path:
    return config_dir() / "config.json"


def load() -> Config:
    p = config_path()
    if not p.exists():
        return Config()
    data = json.loads(p.read_text(encoding="utf-8"))
    known = {k: v for k, v in data.items() if k in Config.__dataclass_fields__}
    return Config(**known)


def save(cfg: Config) -> None:
    p = config_path()
    p.write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")
    restrict_permissions(p)


def normalize_domain(value: str) -> str:
    v = value.strip()
    for prefix in ("https://", "http://"):
        if v.lower().startswith(prefix):
            v = v[len(prefix):]
    return v.split("/")[0].strip()


def import_legacy(folder: str) -> Config:
    """Import settings from the earlier script-based setup (E:\\zotero_mcp)."""
    import re
    f = Path(folder)
    cfg = load()
    env = f / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("ZOTERO_MCP_ADMIN_PASSWORD="):
                cfg.admin_password = line.split("=", 1)[1].strip()
            elif line.startswith("ZOTERO_MCP_PUBLIC_URL="):
                cfg.domain = normalize_domain(line.split("=", 1)[1])
    pol = f / "ngrok-policy.yml"
    if pol.exists():
        m = re.search(r'^\s+- "([^":]+):([^"]+)"\s*$', pol.read_text(encoding="utf-8", errors="ignore"), re.M)
        if m:
            cfg.basic_user, cfg.basic_password = m.group(1), m.group(2)
    return cfg
