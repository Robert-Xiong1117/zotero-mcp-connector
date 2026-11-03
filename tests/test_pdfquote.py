"""Coordinate conversion and quote matching, on PDFs generated with PyMuPDF."""
import re

import pymupdf
import pytest

from app import pdfquote


def _save(doc, tmp_path, name="t.pdf"):
    p = tmp_path / name
    doc.save(p)
    return str(p)


def _lines_pdf(tmp_path, pages, fontname="helv"):
    """pages: list of list of lines; each line drawn at y = 100 + 20*i (top-left coords)."""
    doc = pymupdf.open()
    for lines in pages:
        page = doc.new_page(width=595, height=842)
        for i, text in enumerate(lines):
            page.insert_text((72, 100 + 20 * i), text, fontname=fontname, fontsize=11)
    return _save(doc, tmp_path)


def _raw_pdf(tmp_path, rotate=0, crop=None, mediabox=None):
    """Text drawn by a hand-written content stream: baseline at PDF user-space (100, 700)."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((0, 0), " ")
    font = page.get_fonts()[0][4]
    doc.update_stream(page.get_contents()[0], f"BT /{font} 12 Tf 100 700 Td (Hello world) Tj ET".encode())
    if mediabox:
        doc.xref_set_key(page.xref, "MediaBox", "[%g %g %g %g]" % mediabox)
    if crop:
        doc.xref_set_key(page.xref, "CropBox", "[%g %g %g %g]" % crop)
    doc.xref_set_key(page.xref, "Rotate", str(rotate))
    return _save(doc, tmp_path)


# ---------- coordinates ----------
@pytest.mark.parametrize("rotate,crop,mediabox", [
    (0, None, None),
    (90, None, None),
    (180, None, None),
    (270, (50, 30, 562, 742), None),
    (90, (60, 40, 500, 750), (10, 20, 612, 792)),
])
def test_rect_is_pdf_user_space(tmp_path, rotate, crop, mediabox):
    hit, _ = pdfquote.locate(_raw_pdf(tmp_path, rotate, crop, mediabox), "Hello world")
    (x1, y1, x2, y2), = hit.rects
    assert hit.method == "exact" and hit.page_index == 0
    assert abs(x1 - 100) < 0.5                    # starts at the Td x
    assert y1 < 700 < y2 and y2 - y1 < 20         # line box straddles the baseline (y up)
    assert x2 > x1 + 50


def test_y_flip_matches_page_height(tmp_path):
    path = _lines_pdf(tmp_path, [["The quick brown fox jumps over the lazy dog."]])
    hit, _ = pdfquote.locate(path, "quick brown fox")
    with pymupdf.open(path) as doc:
        r = doc[0].search_for("quick brown fox")[0]
    (x1, y1, x2, y2), = hit.rects
    assert (x1, x2) == (round(r.x0, 3), round(r.x1, 3))
    assert y1 == pytest.approx(842 - r.y1, abs=1e-3) and y2 == pytest.approx(842 - r.y0, abs=1e-3)


# ---------- matching ----------
def test_exact_single_line_and_sort_index(tmp_path):
    path = _lines_pdf(tmp_path, [["Intro page."], ["First line here.", "Evidence shows that trust drives adoption."]])
    hit, cands = pdfquote.locate(path, "trust drives adoption")
    assert hit.method == "exact" and hit.page_index == 1 and hit.page_label == "2" and not cands
    assert re.fullmatch(r"00001\|\d{6}\|\d{5}", hit.sort_index)
    assert int(hit.sort_index.split("|")[2]) == pytest.approx(120 - 11, abs=4)   # top of line 2


def test_exact_across_lines_gives_one_rect_per_line(tmp_path):
    path = _lines_pdf(tmp_path, [["Consumers increasingly rely on", "synthetic personas for early tests."]])
    hit, _ = pdfquote.locate(path, "rely on synthetic personas")
    assert len(hit.rects) == 2
    assert hit.rects[0][1] > hit.rects[1][1]       # first line is higher up (larger y in PDF space)


def test_only_first_occurrence_is_highlighted(tmp_path):
    path = _lines_pdf(tmp_path, [["alpha beta gamma", "delta. Then again alpha beta", "gamma delta."]])
    hit, _ = pdfquote.locate(path, "alpha beta gamma delta")
    assert hit.occurrences == 2 and len(hit.rects) == 2
    assert hit.rects[0][1] > 700                    # first line of page, not the later occurrence


def test_dehyphenated_line_break(tmp_path):
    path = _lines_pdf(tmp_path, [["This disserta-", "tion examines after-sales service."]])
    hit, _ = pdfquote.locate(path, "This dissertation examines")
    assert hit.method == "normalized" and len(hit.rects) == 2


def test_whitespace_case_and_quotes_normalized(tmp_path):
    path = _lines_pdf(tmp_path, [['He called it "good enough" for pilots.']])
    hit, _ = pdfquote.locate(path, "he   called it\n“GOOD enough”")
    assert hit.method == "normalized" and hit.page_index == 0


def test_quote_across_page_break(tmp_path):
    path = _lines_pdf(tmp_path, [["Page one text ends with the start of", "a sentence that continues"],
                                 ["onto the next page clearly.", "Other text."]])
    hit, _ = pdfquote.locate(path, "a sentence that continues onto the next page")
    assert hit.page_index == 0 and hit.method == "normalized"
    assert len(hit.rects) == 1 and len(hit.next_page_rects) == 1


def test_chinese_text(tmp_path):
    path = _lines_pdf(tmp_path, [["售后服务质量显著影响", "消费者的品牌忠诚度。"]], fontname="china-s")
    hit, _ = pdfquote.locate(path, "售后服务质量显著影响 消费者的品牌忠诚度")
    assert len(hit.rects) == 2
    hit, _ = pdfquote.locate(path, "服务质量​显著影响\n消费者的品牌")   # zero-width space: stage 2
    assert hit.method == "normalized" and len(hit.rects) == 2


def test_not_found_returns_candidates(tmp_path):
    path = _lines_pdf(tmp_path, [["Battery warranty strongly shapes repurchase intention.",
                                  "Dealers matter less than expected."]])
    hit, cands = pdfquote.locate(path, "Battery warranties strongly shape the repurchase intention")
    assert hit is None
    assert cands and "Battery warranty strongly shapes" in cands[0]["text"] and cands[0]["page"] == "1"
    assert 0.5 < cands[0]["score"] < 1


def test_bad_input(tmp_path):
    path = _lines_pdf(tmp_path, [["Some text."]])
    with pytest.raises(ValueError):
        pdfquote.locate(path, "  a ")
    empty = pymupdf.open(); empty.new_page()
    with pytest.raises(ValueError, match="text layer"):
        pdfquote.locate(_save(empty, tmp_path, "empty.pdf"), "anything at all")


def test_normalize():
    assert pdfquote.normalize("Co-\nopération ﬁnal “X”") == "coopérationfinalx"


def test_pdf_style_quotes_and_dropped_apostrophe(tmp_path):
    # as extracted from real journal PDFs: “x” rendered as ‘‘x’’, possessive apostrophe missing
    path = _lines_pdf(tmp_path, [["The term ‘‘technology readiness’’", "(TR) refers to peoples pro-",
                                  "pensity to embrace new tools."]], fontname="china-s")   # CJK font has curly quotes
    hit, _ = pdfquote.locate(path, 'The term "technology readiness" (TR) refers to people\'s propensity to embrace')
    assert hit is not None and hit.method == "normalized" and len(hit.rects) == 3
