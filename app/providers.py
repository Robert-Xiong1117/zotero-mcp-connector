"""AI platforms whose servers may reach the tunnel (ngrok restrict-ips allow-list).

Anthropic is always allowed (Config.allow_cidrs). ChatGPT can be switched on: OpenAI publishes its
connector egress ranges at OPENAI_URL and changes them, so we download the list on start and once a
day, keep the last good copy in the config, and reload the tunnel only when it actually changed.
The allow-list only says "this request comes from OpenAI's servers"; who may use the connector is
still decided by OAuth (Basic Auth + admin password at authorization time).

DeepSeek Harness is not here on purpose: it runs on this computer and never comes through the tunnel.
"""
import ipaddress
import json
import time
import urllib.request

OPENAI_URL = "https://openai.com/chatgpt-connectors.json"
REFRESH_SECONDS = 24 * 3600
MIN_PREFIXES = 10            # a much shorter list is treated as a broken download, not a real change


class ProviderError(Exception):
    pass


def fetch_openai(url: str = OPENAI_URL, timeout: float = 20.0) -> tuple:
    """(creationTime, [cidr, ...]) from OpenAI's published file; raises ProviderError if unusable."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ZoteroMCP"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        raise ProviderError(f"无法下载 ChatGPT IP 列表：{type(e).__name__}: {e}") from None
    cidrs = []
    for p in data.get("prefixes") or []:
        raw = p.get("ipv4Prefix") or p.get("ipv6Prefix")
        try:
            cidrs.append(str(ipaddress.ip_network(raw, strict=False)))
        except (TypeError, ValueError):
            continue
    cidrs = sorted(set(cidrs), key=lambda c: (":" in c, c))
    if len(cidrs) < MIN_PREFIXES:
        raise ProviderError(f"ChatGPT IP 列表异常（只有 {len(cidrs)} 条），保留上次的列表")
    return str(data.get("creationTime") or ""), cidrs


def allow_list(cfg) -> list:
    """Everything the tunnel should let through (auth-mode IP is added by ngrok.write_policy)."""
    out = list(cfg.allow_cidrs)
    if cfg.openai_enabled:
        out += [c for c in cfg.openai_cidrs if c not in out]
    return out


def refresh_openai(cfg, force: bool = False, fetch=None) -> bool:
    """Update cfg's cached ChatGPT ranges if due. Returns True if the list changed (caller saves and
    reloads the tunnel). Raises ProviderError only if there is no usable list at all."""
    if not cfg.openai_enabled:
        return False
    if not force and cfg.openai_cidrs and time.time() - cfg.openai_checked_at < REFRESH_SECONDS:
        return False
    try:
        created, cidrs = (fetch or fetch_openai)()
    except ProviderError:
        if cfg.openai_cidrs:
            return False                       # keep the last good list; try again next time
        raise
    cfg.openai_checked_at = time.time()
    changed = cidrs != cfg.openai_cidrs
    cfg.openai_cidrs, cfg.openai_list_time = cidrs, created
    return changed
