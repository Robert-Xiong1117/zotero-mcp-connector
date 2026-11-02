"""Bounded, read-only Zotero Web API access with explicit pagination."""
from collections import OrderedDict
from io import BytesIO
import json
import math
import re
import threading
import time
from urllib.parse import urljoin, urlsplit

import httpx

API = "https://api.zotero.org"
MAX_PDF_BYTES = 32 * 1024 * 1024
CACHE_BYTES = 64 * 1024 * 1024


class CloudError(RuntimeError):
    """Safe diagnostic that does not contain tokens or signed URLs."""


def item_key(value):
    if not re.fullmatch(r"[A-Z0-9]{8}", value):
        raise ValueError("Expected an 8-character Zotero key")
    return value


class CloudClient:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.prefix = f"/{settings.library_type}s/{settings.library_id}"
        # No default secret header: credentials must never follow storage redirects.
        self.http = httpx.Client(timeout=30, follow_redirects=False, transport=transport,
                                 trust_env=False)
        self._lock = threading.RLock()
        self._not_before = 0.0
        self._cache = OrderedDict()

    def close(self):
        self.http.close()

    def _headers(self):
        return {"Zotero-API-Key": self.settings.api_key, "Zotero-API-Version": "3"}

    def _gate(self):
        with self._lock:
            wait = math.ceil(self._not_before - time.monotonic())
        if wait > 0:
            raise CloudError(f"Zotero requested a pause; retry in {wait} seconds")

    def _status(self, response):
        pauses = []
        for name in ("Backoff", "Retry-After"):
            try:
                pauses.append(max(0, int(response.headers.get(name, "0"))))
            except ValueError:
                pass
        if response.status_code == 429 and not any(pauses):
            pauses.append(30)
        with self._lock:
            self._not_before = max(self._not_before, time.monotonic() + max(pauses, default=0))
        if response.status_code in (401, 403):
            raise CloudError("Access denied: check API key and library/note/file permissions")
        if response.status_code == 404:
            raise CloudError("Not available in Zotero cloud: check sync, item key, and attachment storage")
        if response.status_code >= 400:
            raise CloudError(f"Zotero request failed (HTTP {response.status_code}); retry later if temporary")

    def _get(self, path, params=None):
        self._gate()
        try:
            response = self.http.get(API + self.prefix + path, headers=self._headers(), params=params)
        except httpx.HTTPError:
            raise CloudError("Could not reach Zotero cloud; retry later") from None
        self._status(response)
        if response.is_redirect:
            raise CloudError("Unexpected redirect from metadata API")
        return response

    def _json(self, response):
        try:
            return response.json()
        except ValueError:
            raise CloudError("Zotero returned invalid JSON") from None

    def page(self, path, start=0, limit=50, **params):
        if start < 0 or not 1 <= limit <= 100:
            raise ValueError("start must be >= 0; limit must be 1..100")
        response = self._get(path, {**params, "start": start, "limit": limit})
        data = self._json(response)
        if not isinstance(data, list):
            raise CloudError("Expected a list from Zotero")
        total_header = response.headers.get("Total-Results")
        total = int(total_header) if total_header is not None else None
        more = start + len(data) < total if total is not None else len(data) == limit
        return {"data": [self.with_links(v) for v in data], "total": total,
                "next_start": start + len(data) if more and data else None,
                "library_version": response.headers.get("Last-Modified-Version")}

    def with_links(self, obj):
        if not isinstance(obj, dict) or "key" not in obj:
            return obj
        result = dict(obj)
        key = item_key(obj["key"])
        scope = "library" if self.settings.library_type == "user" else f"groups/{self.settings.library_id}"
        data = obj.get("data", {})
        kind = "items" if "itemType" in data else "searches" if "conditions" in data else "collections"
        result["source"] = {"api": API + self.prefix + f"/{kind}/" + key}
        if kind != "searches":
            result["source"]["desktop"] = f"zotero://select/{scope}/{kind}/{key}"
        if data.get("itemType") == "annotation" and data.get("parentItem"):
            parent = item_key(data["parentItem"])
            try:
                pos = json.loads(data.get("annotationPosition", "{}"))
                page = int(pos["pageIndex"]) + 1
            except (ValueError, TypeError, KeyError):
                page = None
            link = f"zotero://open-pdf/{scope}/items/{parent}?annotation={key}"
            if page is not None:
                link += f"&page={page}"
            result["source"].update(annotation=link, pdf_page=page,
                                    page_label=data.get("annotationPageLabel"))
        return result

    def item(self, key):
        return self.with_links(self._json(self._get(f"/items/{item_key(key)}")))

    def fulltext(self, key, offset=0, max_chars=20000):
        if offset < 0 or not 1 <= max_chars <= 50000:
            raise ValueError("offset must be >= 0; max_chars must be 1..50000")
        data = self._json(self._get(f"/items/{item_key(key)}/fulltext"))
        content = data.pop("content", "")
        stop = offset + max_chars
        return {**data, "content": content[offset:stop], "total_chars": len(content),
                "next_offset": stop if stop < len(content) else None,
                "warning": "Indexed text may be incomplete and has no reliable page boundaries. Use read_pdf_pages for page evidence."}

    def export(self, keys, format="bibtex"):
        if format not in ("bibtex", "ris", "csljson"):
            raise ValueError("format must be bibtex, ris, or csljson")
        if not 1 <= len(keys) <= 50:
            raise ValueError("Export 1..50 item keys per call")
        return self._get("/items", {"itemKey": ",".join(item_key(k) for k in keys),
                                   "format": format, "limit": 50}).text

    @staticmethod
    def _storage_url(url):
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        # Only HTTPS Zotero/S3 storage destinations. Never user-supplied URLs.
        return (parsed.scheme == "https" and not parsed.username and not parsed.password
                and parsed.port in (None, 443)
                and (host == "api.zotero.org" or host.endswith(".zotero.org")
                     or host.endswith(".s3.amazonaws.com")
                     or (host.endswith(".amazonaws.com") and ".s3." in host)))

    def pdf_bytes(self, key):
        obj = self.item(key)
        data = obj["data"]
        if data.get("itemType") != "attachment" or data.get("contentType") != "application/pdf":
            raise CloudError("Use a PDF attachment key, not the parent article key")
        if data.get("linkMode") not in ("imported_file", "imported_url"):
            raise CloudError("Linked attachments are not stored in Zotero cloud")
        cache_key = (key, obj.get("version"), data.get("md5"))
        with self._lock:
            if cache_key in self._cache:
                self._cache.move_to_end(cache_key)
                return self._cache[cache_key]
        url = API + self.prefix + f"/items/{item_key(key)}/file"
        content = None
        for _ in range(5):
            if not self._storage_url(url):
                raise CloudError("Attachment redirect is not an approved HTTPS storage destination")
            self._gate()
            headers = self._headers() if urlsplit(url).hostname == "api.zotero.org" else {}
            try:
                with self.http.stream("GET", url, headers=headers) as response:
                    self._status(response)
                    if response.is_redirect:
                        location = response.headers.get("Location")
                        if not location:
                            raise CloudError("Storage redirect missing Location")
                        url = urljoin(url, location)
                        continue
                    try:
                        size = int(response.headers.get("Content-Length", "0"))
                    except ValueError:
                        size = 0
                    if size > MAX_PDF_BYTES:
                        raise CloudError("PDF exceeds the 32 MiB download limit")
                    buf = bytearray()
                    for chunk in response.iter_bytes(65536):
                        buf.extend(chunk)
                        if len(buf) > MAX_PDF_BYTES:
                            raise CloudError("PDF exceeds the 32 MiB download limit")
                    content = bytes(buf)
                    break
            except httpx.HTTPError:
                raise CloudError("PDF download failed; verify file sync and retry") from None
        if content is None:
            raise CloudError("Too many attachment redirects")
        if not content.lstrip().startswith(b"%PDF-"):
            raise CloudError("Downloaded file is not a PDF; verify attachment sync/storage")
        with self._lock:
            self._cache[cache_key] = content
            while sum(map(len, self._cache.values())) > CACHE_BYTES:
                self._cache.popitem(last=False)
        return content

    def pdf_pages(self, key, start_page=1, page_count=5):
        if start_page < 1 or not 1 <= page_count <= 10:
            raise ValueError("start_page must be >= 1; page_count must be 1..10")
        from pypdf import PdfReader
        try:
            reader = PdfReader(BytesIO(self.pdf_bytes(key)))
            if reader.is_encrypted:
                raise CloudError("Encrypted PDF is unsupported")
            total = len(reader.pages)
            if start_page > total:
                raise ValueError("start_page exceeds PDF length")
            end = min(total, start_page - 1 + page_count)
            pages = []
            for i in range(start_page - 1, end):
                text = reader.pages[i].extract_text() or ""
                pages.append({"pdf_page": i + 1, "text": text[:30000],
                              "truncated": len(text) > 30000,
                              "needs_ocr": not text.strip()})
        except (CloudError, ValueError):
            raise
        except Exception:
            raise CloudError("PDF parsing failed; the file may require OCR or repair") from None
        return {"attachment_key": key, "total_pages": total, "pages": pages,
                "next_page": end + 1 if end < total else None,
                "page_numbering": "1-based PDF pages, not printed page labels; no OCR performed"}
