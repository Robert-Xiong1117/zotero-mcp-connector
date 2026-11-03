"""Read annotations through Zotero's local API instead of zotero.sqlite.

zotero-mcp-lite reads annotations straight from zotero.sqlite. That breaks in two ways:
  - it ignores Zotero's own data-directory pref (extensions.zotero.dataDir) and may find a stale
    copy in ~/Zotero, so claude.ai sees old annotations;
  - while Zotero runs, the live database cannot be opened read-only (nolock), and immutable mode
    misses everything still in the WAL, i.e. the newest highlights.
Both of its annotation readers go through zotero_mcp.local_db.get_local_db(), imported at call
time, so install() swaps that for a reader with the same interface backed by the local API
(always the live library). Output formatting stays zotero-mcp-lite's own.
"""
import json
import urllib.parse

from .bridge import _NOPROXY, _base

ANNOTATED_TYPES = ("application/pdf", "application/epub+zip", "text/html")
PAGE = 100


def _get(path: str, params: dict | None = None, timeout: float = 15.0):
    """GET /api/users/0/<path>; returns (json, total_results)."""
    url = f"{_base()}/api/users/0/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with _NOPROXY.open(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8") or "null"), int(r.headers.get("Total-Results") or 0)


def _all(path: str, params: dict, cap: int = 5000) -> list:
    out, start = [], 0
    while True:
        page, total = _get(path, {**params, "limit": PAGE, "start": start})
        out.extend(page or [])
        start += PAGE
        if not page or start >= min(total, cap):
            return out


def _by_keys(keys) -> dict:
    """{key: item}, one request per key: Zotero's local API ignores the itemKey filter
    (it returns arbitrary items), unlike the web API."""
    from concurrent.futures import ThreadPoolExecutor

    def one(k):
        try:
            return k, _get(f"items/{k}")[0]
        except Exception:
            return k, None    # deleted / not visible: its annotations are skipped
    with ThreadPoolExecutor(max_workers=8) as pool:
        return {k: it for k, it in pool.map(one, set(k for k in keys if k)) if it}


def _annotation(a: dict, attachment: dict | None, parent: dict | None = None):
    from zotero_mcp.local_db import Annotation, _parse_annotation_type
    d = a.get("data", {})
    att = (attachment or {}).get("data", {})
    return Annotation(type=_parse_annotation_type(d.get("annotationType")), text=d.get("annotationText"),
                      comment=d.get("annotationComment"), color=d.get("annotationColor"),
                      page_label=d.get("annotationPageLabel"), attachment_name=att.get("filename") or att.get("title"),
                      parent_key=(parent or {}).get("key"),
                      parent_title=(parent or {}).get("data", {}).get("title"))


def _sort_key(a: dict) -> str:
    return a.get("data", {}).get("annotationSortIndex") or ""


class LocalApiAnnotations:
    """Drop-in for zotero_mcp.local_db.LocalZoteroDB's annotation methods."""

    def get_annotations_for_item(self, item_key: str) -> list:
        item, _ = _get(f"items/{item_key}")
        if item["data"].get("itemType") == "attachment":
            atts = [item]
        else:
            atts = [c for c in _all(f"items/{item_key}/children", {})
                    if c["data"].get("itemType") == "attachment" and c["data"].get("contentType") in ANNOTATED_TYPES]
        out = []
        for att in atts:
            annos = _all(f"items/{att['key']}/children", {"itemType": "annotation"})
            out.extend(_annotation(a, att) for a in sorted(annos, key=_sort_key))
        return out

    def search_annotations(self, query: str, limit: int = 50) -> list:
        needle, hits, start = query.casefold(), [], 0
        while len(hits) < limit:       # the API's q also matches tags etc.; keep lite's text/comment semantics
            page, total = _get("items", {"itemType": "annotation", "q": query, "qmode": "everything",
                                         "limit": PAGE, "start": start})
            hits += [a for a in page or [] if needle in (a["data"].get("annotationText") or "").casefold()
                     or needle in (a["data"].get("annotationComment") or "").casefold()]
            start += PAGE
            if not page or start >= total:
                break
        atts = _by_keys(a["data"].get("parentItem") for a in hits)
        parents = _by_keys(att["data"].get("parentItem") for att in atts.values())
        rows = []
        for a in hits:
            att = atts.get(a["data"].get("parentItem"))
            if not att or att["data"].get("contentType") not in ANNOTATED_TYPES:
                continue
            parent = parents.get(att["data"].get("parentItem"))
            if parent:
                rows.append((parent["key"], _sort_key(a), a, att, parent))
        rows.sort(key=lambda r: (r[0], r[1]))
        return [_annotation(a, att, parent) for _, _, a, att, parent in rows[:limit]]

    def close(self) -> None:
        pass


def install() -> None:
    """Route zotero-mcp-lite's annotation reads through the local API (called in the server child)."""
    from zotero_mcp import local_db
    local_db.get_local_db = lambda: LocalApiAnnotations()
