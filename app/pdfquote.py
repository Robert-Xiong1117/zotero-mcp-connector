"""Locate a quoted sentence in a PDF and express it as a Zotero highlight position.

Matching runs in two stages:
  1. exact      — PyMuPDF page.search_for(quote)
  2. normalized — Unicode NFKC, case-folded, all whitespace, hyphens and quote marks removed,
                  so line breaks, de-hyphenation ("disserta-\\ntion") and cross-line/page quotes match.
Nothing fuzzy is ever written: if both stages fail, the closest sentences are returned as candidates.

Coordinates: PyMuPDF reports unrotated page space (origin top-left of the CropBox, y down).
Zotero stores PDF user space (y up). We convert with the inverse of the page's transformation
matrix taken with /Rotate cleared, which handles CropBox/MediaBox offsets (y = top - y).
"""
import difflib
import re
import unicodedata
from dataclasses import dataclass, field

import pymupdf

HYPHENS = "-­‐‑‒–—−"
# Quote marks are ignored entirely: PDFs render “x” as ‘‘x’’, drop apostrophes ("peoples") or
# extract them as U+FFFD (also ignored).
QUOTES = "'\"`´‘’‚‛′“”„‟″«»「」『』"
_SENT_END = re.compile(r"(?<=[.!?;。！？；])\s+|(?<=[。！？；])")


def key_chars(ch: str) -> str:
    """Normalized form of one character ('' if it is whitespace or a hyphen)."""
    out = []
    for c in unicodedata.normalize("NFKC", ch).casefold():
        if c.isspace() or c in HYPHENS or c in QUOTES or c == "�" or unicodedata.category(c) in ("Cc", "Cf"):
            continue
        out.append(c)
    return "".join(out)


def normalize(text: str) -> str:
    return "".join(key_chars(c) for c in text)


@dataclass
class Located:
    page_index: int
    page_label: str
    method: str                       # exact | normalized
    rects: list                       # PDF user space [[x1, y1, x2, y2], ...], one per line
    sort_index: str
    next_page_rects: list = field(default_factory=list)
    occurrences: int = 1


class _Char:
    __slots__ = ("page", "line", "bbox")

    def __init__(self, page, line, bbox):
        self.page, self.line, self.bbox = page, line, bbox


def _to_pdf_matrix(page):
    """Matrix mapping PyMuPDF (unrotated) page coords to PDF user space."""
    rot = page.rotation
    if rot:
        page.set_rotation(0)          # in-memory only; the document is never saved
    m = ~page.transformation_matrix
    if rot:
        page.set_rotation(rot)
    return m


def to_pdf_rect(rect, matrix) -> list:
    r = pymupdf.Rect(rect) * matrix
    r.normalize()
    return [round(r.x0, 3), round(r.y0, 3), round(r.x1, 3), round(r.y1, 3)]


def _page_label(page) -> str:
    try:
        return page.get_label() or str(page.number + 1)
    except Exception:
        return str(page.number + 1)


def _page_chars(page):
    """[(key_char, _Char)] for one page in reading order, from rawdict."""
    out = []
    raw = page.get_text("rawdict", flags=pymupdf.TEXT_PRESERVE_LIGATURES | pymupdf.TEXT_PRESERVE_WHITESPACE)
    for b in raw.get("blocks", []):
        for li, line in enumerate(b.get("lines", [])):
            lid = (b.get("number", 0), li)
            for span in line.get("spans", []):
                for ch in span.get("chars", []):
                    for k in key_chars(ch["c"]):
                        out.append((k, _Char(page.number, lid, pymupdf.Rect(ch["bbox"]))))
    return out


def _line_rects(chars) -> list:
    """Union of character boxes per text line, in order."""
    lines, order = {}, []
    for c in chars:
        k = (c.page, c.line)
        if k not in lines:
            lines[k] = pymupdf.Rect(c.bbox)
            order.append(k)
        else:
            lines[k] |= c.bbox
    return [(k[0], lines[k]) for k in order]


def _sort_index(page_index: int, offset: int, top: float) -> str:
    return f"{page_index:05d}|{max(0, offset):06d}|{max(0, int(top)):05d}"


def _exact(doc, quote: str):
    target = len(normalize(quote))
    for page in doc:
        hits = page.search_for(quote)
        if not hits:
            continue
        chars = _page_chars(page)
        # search_for returns one rect per line for every occurrence; take lines until the first one is covered
        first, covered = [], 0
        for r in hits:
            first.append(r)
            covered += sum(1 for _, c in chars if r.contains(pymupdf.Point((c.bbox.x0 + c.bbox.x1) / 2,
                                                                           (c.bbox.y0 + c.bbox.y1) / 2)))
            if covered >= target:
                break
        m = _to_pdf_matrix(page)
        page_key = "".join(k for k, _ in chars)
        offset = page_key.find(normalize(quote))
        occ = max(1, page_key.count(normalize(quote)))
        return Located(page.number, _page_label(page), "exact", [to_pdf_rect(r, m) for r in first],
                       _sort_index(page.number, offset, first[0].y0), occurrences=occ)
    return None


def _normalized(doc, quote: str):
    needle = normalize(quote)
    stream, page_start = [], {}
    for page in doc:
        page_start[page.number] = len(stream)
        stream.extend(_page_chars(page))
    hay = "".join(k for k, _ in stream)
    i = hay.find(needle)
    if i < 0:
        return None
    lines = _line_rects([c for _, c in stream[i:i + len(needle)]])
    first_page = lines[0][0]
    m = _to_pdf_matrix(doc[first_page])
    rects = [to_pdf_rect(r, m) for p, r in lines if p == first_page]
    nxt = [(p, r) for p, r in lines if p == first_page + 1]
    next_rects = [to_pdf_rect(r, _to_pdf_matrix(doc[first_page + 1])) for _, r in nxt] if nxt else []
    top = min(r.y0 for p, r in lines if p == first_page)
    return Located(first_page, _page_label(doc[first_page]), "normalized", rects,
                   _sort_index(first_page, i - page_start[first_page], top), next_rects, hay.count(needle))


def candidates(doc, quote: str, limit: int = 3) -> list:
    """Closest sentences (never written), best first."""
    needle = normalize(quote)
    scored = []
    for page in doc:
        text = re.sub(r"[" + re.escape(HYPHENS) + r"]\s*\n\s*", "", page.get_text())
        text = re.sub(r"\s+", " ", text)
        for sent in _SENT_END.split(text):
            s = sent.strip()
            ks = normalize(s)
            if len(ks) < 8:
                continue
            sm = difflib.SequenceMatcher(None, needle, ks, autojunk=False)
            if sm.real_quick_ratio() < 0.3 or sm.quick_ratio() < 0.3:
                continue
            scored.append((sm.ratio(), page.number, s))
    scored.sort(key=lambda t: -t[0])
    return [{"page": _page_label(doc[p]), "page_index": p, "score": round(sc, 3), "text": s[:400]}
            for sc, p, s in scored[:limit]]


def locate(pdf_path: str, quote: str):
    """Return (Located | None, candidates). Raises ValueError for unusable input."""
    quote = (quote or "").strip()
    if len(normalize(quote)) < 4:
        raise ValueError("quote is too short to locate reliably")
    with pymupdf.open(pdf_path) as doc:
        if not any(p.get_text().strip() for p in doc):
            raise ValueError("PDF has no text layer (scanned without OCR?)")
        hit = _exact(doc, quote) or _normalized(doc, quote)
        return (hit, []) if hit else (None, candidates(doc, quote))
