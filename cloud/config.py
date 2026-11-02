"""Explicit cloud configuration. Never read desktop preferences or secrets."""
from dataclasses import dataclass, field
import os
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    library_id: str
    api_key: str = field(repr=False)
    public_url: str
    admin_password: str = field(repr=False)
    library_type: str = "user"
    port: int = 8000
    data_dir: str = "/data"
    cimd_urls: tuple[str, ...] = ()

    def __post_init__(self):
        if not self.library_id.isdecimal() or int(self.library_id) < 1:
            raise ValueError("ZOTERO_LIBRARY_ID must be your positive cloud user/group ID, not local ID 0")
        if self.library_type not in ("user", "group"):
            raise ValueError("ZOTERO_LIBRARY_TYPE must be user or group")
        if not self.api_key.strip():
            raise ValueError("ZOTERO_API_KEY is required")
        u = urlsplit(self.public_url)
        if (u.scheme != "https" or not u.hostname or u.username or u.password
                or u.path not in ("", "/") or u.query or u.fragment):
            raise ValueError("ZOTERO_MCP_PUBLIC_URL must be an HTTPS origin without /mcp")
        if len(self.admin_password) < 24:
            raise ValueError("Use a random ZOTERO_MCP_ADMIN_PASSWORD of at least 24 characters")
        if not 1 <= self.port <= 65535:
            raise ValueError("PORT must be between 1 and 65535")
        for value in self.cimd_urls:
            parsed = urlsplit(value)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("CIMD allowlist entries must be trusted HTTPS URLs")

    @classmethod
    def from_env(cls):
        return cls(
            library_id=os.getenv("ZOTERO_LIBRARY_ID", ""),
            library_type=os.getenv("ZOTERO_LIBRARY_TYPE", "user"),
            api_key=os.getenv("ZOTERO_API_KEY", ""),
            public_url=os.getenv("ZOTERO_MCP_PUBLIC_URL", "").rstrip("/"),
            admin_password=os.getenv("ZOTERO_MCP_ADMIN_PASSWORD", ""),
            port=int(os.getenv("PORT", "8000")),
            data_dir=os.getenv("ZOTERO_CLOUD_DATA_DIR", "/data"),
            cimd_urls=tuple(v.strip() for v in os.getenv("ZOTERO_CIMD_URLS", "").split(",") if v.strip()),
        )
