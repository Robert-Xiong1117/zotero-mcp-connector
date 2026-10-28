"""Encrypted export/import of the whole setup (config + OAuth grants) for moving to a new computer."""
import base64
import io
import json
import os
import zipfile

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from . import config as cfgmod
from .paths import oauth_db_path, restrict_permissions

MAGIC = b"ZMCP1"


def _key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600_000)
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def export_bundle(passphrase: str) -> bytes:
    if len(passphrase) < 8:
        raise ValueError("口令至少 8 位")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("config.json", cfgmod.config_path().read_text(encoding="utf-8"))
        db = oauth_db_path()
        if db.exists():
            z.write(db, "oauth.sqlite")
    salt = os.urandom(16)
    return MAGIC + salt + Fernet(_key(passphrase, salt)).encrypt(buf.getvalue())


def import_bundle(blob: bytes, passphrase: str) -> None:
    if not blob.startswith(MAGIC):
        raise ValueError("不是有效的配置包")
    salt, token = blob[5:21], blob[21:]
    try:
        raw = Fernet(_key(passphrase, salt)).decrypt(token)
    except InvalidToken:
        raise ValueError("口令错误或文件已损坏")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        data = json.loads(z.read("config.json").decode("utf-8"))
        cfg = cfgmod.Config(**{k: v for k, v in data.items() if k in cfgmod.Config.__dataclass_fields__})
        cfg.auth_mode_ip, cfg.auth_mode_until, cfg.paused = "", 0.0, False
        cfgmod.save(cfg)
        if "oauth.sqlite" in z.namelist():
            db = oauth_db_path()
            db.parent.mkdir(parents=True, exist_ok=True)
            db.write_bytes(z.read("oauth.sqlite"))
            restrict_permissions(db)
