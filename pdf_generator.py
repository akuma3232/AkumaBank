"""
pdf_generator.py - Official PDF Document Generator for AkumaBank
Generates official Moroccan banking certificates, card subscription agreements,
RIB attestations, account closure certificates, and transaction statements.
Built using ReportLab.

Design system
-------------
Every document shares the same professional page chrome:
  * a deep-navy cover banner carrying the bank identity and the official reference;
  * a slim banner repeated on every following page;
  * a footer with legal notice, page numbering and the document identifier;
  * refined typography (embedded DejaVu family when available, graceful fallback),
    hairline tables, tinted label columns and a bank seal / signature block.

Branding slots
--------------
  * Emblem: the top-right corner of page 1 is reserved and left blank. Either
    let the holder place their own crest from a PDF reader, or drop the file in
    ``static/branding/emblem.png`` (also emblem.jpg / logo.png, ...) and it is
    drawn there automatically.
  * Signature: nothing is printed at the bottom of the page — no signatory
    name, no drawn signature, no seal. The lower part of the sheet is left
    free for an electronic signature added after the document is issued.
"""

import math
import os
from io import BytesIO
from datetime import datetime
from xml.sax.saxutils import escape as _escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as _canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    KeepTogether,
    NextPageTemplate,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.graphics.barcode.code128 import Code128
from reportlab.graphics.shapes import Circle, Drawing, Group, Line, Path, Rect, String

from morocco_banking import format_moroccan_rib, format_iban, rib_to_iban, format_card_number


# ─────────────────────────────────────────────────────────────────────────────
# PALETTE
# ─────────────────────────────────────────────────────────────────────────────

INK = colors.HexColor("#0B1F3A")        # Deep institutional navy
NAVY = colors.HexColor("#14335E")
NAVY_SOFT = colors.HexColor("#1D4B8F")
BLUE = colors.HexColor("#2563EB")
GOLD = colors.HexColor("#B8893B")
GOLD_LIGHT = colors.HexColor("#E3C98D")
TEXT = colors.HexColor("#1F2937")
MUTED = colors.HexColor("#64748B")
FAINT = colors.HexColor("#94A3B8")
LINE = colors.HexColor("#E2E8F0")
PANEL = colors.HexColor("#F5F7FA")
PANEL_ALT = colors.HexColor("#EDF1F7")
WHITE = colors.white
GREEN = colors.HexColor("#12715A")
RED = colors.HexColor("#A32020")


# ─────────────────────────────────────────────────────────────────────────────
# TYPOGRAPHY (embedded fonts when present, base-14 fallback otherwise)
# ─────────────────────────────────────────────────────────────────────────────

_FONT_SETS = {
    "sans": (
        "Akuma",
        ("DejaVuSansCondensed.ttf", "DejaVuSansCondensed-Bold.ttf",
         "DejaVuSansCondensed-Oblique.ttf", "DejaVuSansCondensed-BoldOblique.ttf"),
        ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique"),
    ),
    "serif": (
        "AkumaSerif",
        ("DejaVuSerif.ttf", "DejaVuSerif-Bold.ttf",
         "DejaVuSerif-Italic.ttf", "DejaVuSerif-BoldItalic.ttf"),
        ("Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic"),
    ),
    "mono": (
        "AkumaMono",
        ("DejaVuSansMono.ttf", "DejaVuSansMono-Bold.ttf",
         "DejaVuSansMono-Oblique.ttf", "DejaVuSansMono-BoldOblique.ttf"),
        ("Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique"),
    ),
}

_FONT_DIRS = (
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/dejavu",
    "/usr/local/share/fonts",
    "/Library/Fonts",
    "/System/Library/Fonts/Supplemental",
    r"C:\Windows\Fonts",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "fonts"),
)


def _resolve_font_set(family, files, fallbacks):
    """Register a TTF family from the first directory containing every file."""
    names = [fallbacks[0], fallbacks[1], fallbacks[2], fallbacks[3]]
    for directory in _FONT_DIRS:
        try:
            if not all(os.path.exists(os.path.join(directory, f)) for f in files):
                continue
        except OSError:
            continue
        try:
            registered = [family,
                          f"{family}-Bold",
                          f"{family}-Italic",
                          f"{family}-BoldItalic"]
            for name, filename in zip(registered, files):
                if name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(name, os.path.join(directory, filename)))
            pdfmetrics.registerFontFamily(
                family,
                normal=registered[0],
                bold=registered[1],
                italic=registered[2],
                boldItalic=registered[3],
            )
            return tuple(registered)
        except Exception:
            continue
    return tuple(names)


FONT, FONT_BOLD, FONT_ITALIC, FONT_BOLD_ITALIC = _resolve_font_set(*_FONT_SETS["sans"])
SERIF, SERIF_BOLD, SERIF_ITALIC, SERIF_BOLD_ITALIC = _resolve_font_set(*_FONT_SETS["serif"])
MONO, MONO_BOLD, MONO_ITALIC, MONO_BOLD_ITALIC = _resolve_font_set(*_FONT_SETS["mono"])


# ─────────────────────────────────────────────────────────────────────────────
# PAGE GEOMETRY
# ─────────────────────────────────────────────────────────────────────────────

PAGE_W, PAGE_H = A4                # 595.27 x 841.89 pt
MARGIN = 44
CONTENT_W = PAGE_W - 2 * MARGIN    # ≈ 507.27 pt
HEADER_H = 110                     # white header block on page 1
RUN_H = 42                         # compact header on following pages
COVER_TOP = PAGE_H - HEADER_H
RUN_TOP = PAGE_H - RUN_H
FOOTER_H = 46
EMBLEM_SLOT = (118, 66)            # reserved top-right area for your own emblem


# ─────────────────────────────────────────────────────────────────────────────
# STYLES
# ─────────────────────────────────────────────────────────────────────────────

def _get_styles():
    """Build the shared paragraph styles for every document."""
    styles = {}

    styles["Eyebrow"] = ParagraphStyle(
        "Eyebrow", fontName=FONT_BOLD, fontSize=7, leading=9,
        textColor=GOLD, spaceAfter=0,
    )
    styles["DocTitle"] = ParagraphStyle(
        "DocTitle", fontName=SERIF_BOLD, fontSize=19, leading=23,
        textColor=INK, spaceBefore=3, spaceAfter=3,
    )
    styles["DocSub"] = ParagraphStyle(
        "DocSub", fontName=FONT, fontSize=8.2, leading=11,
        textColor=MUTED, spaceAfter=0,
    )
    styles["MetaLabel"] = ParagraphStyle(
        "MetaLabel", fontName=FONT_BOLD, fontSize=6, leading=8.2,
        textColor=MUTED, spaceAfter=1.5,
    )
    styles["MetaValue"] = ParagraphStyle(
        "MetaValue", fontName=FONT_BOLD, fontSize=8.2, leading=10.4,
        textColor=INK,
    )
    styles["SectionTitle"] = ParagraphStyle(
        "SectionTitle", fontName=FONT_BOLD, fontSize=9.4, leading=11.8,
        textColor=INK, spaceAfter=0,
    )
    styles["SectionBadge"] = ParagraphStyle(
        "SectionBadge", fontName=FONT_BOLD, fontSize=8, leading=10,
        textColor=colors.white, alignment=TA_CENTER,
    )
    styles["KvLabel"] = ParagraphStyle(
        "KvLabel", fontName=FONT_BOLD, fontSize=7.2, leading=9.8,
        textColor=NAVY,
    )
    styles["KvValue"] = ParagraphStyle(
        "KvValue", fontName=FONT, fontSize=8.6, leading=11.1,
        textColor=TEXT,
    )
    styles["KvValueStrong"] = ParagraphStyle(
        "KvValueStrong", parent=styles["KvValue"], fontName=FONT_BOLD, textColor=INK,
    )
    styles["KvValueRight"] = ParagraphStyle(
        "KvValueRight", parent=styles["KvValueStrong"], alignment=TA_RIGHT,
    )
    styles["Body"] = ParagraphStyle(
        "Body", fontName=FONT, fontSize=8.8, leading=13,
        textColor=TEXT, spaceAfter=0,
    )
    styles["BodySmall"] = ParagraphStyle(
        "BodySmall", parent=styles["Body"], fontSize=8.4, leading=12.6,
    )
    styles["Legal"] = ParagraphStyle(
        "Legal", fontName=FONT, fontSize=7, leading=9.8,
        textColor=MUTED,
    )
    styles["Notice"] = ParagraphStyle(
        "Notice", fontName=FONT_ITALIC, fontSize=7.6, leading=11.4,
        textColor=MUTED,
    )
    styles["Perk"] = ParagraphStyle(
        "Perk", fontName=FONT, fontSize=8.3, leading=12,
        textColor=TEXT, leftIndent=11, bulletIndent=0,
        bulletFontName=FONT_BOLD, bulletFontSize=8, bulletColor=GOLD,
        spaceAfter=1.5,
    )
    styles["TableHead"] = ParagraphStyle(
        "TableHead", fontName=FONT_BOLD, fontSize=6.9, leading=9,
        textColor=colors.white,
    )
    styles["TableHeadRight"] = ParagraphStyle(
        "TableHeadRight", parent=styles["TableHead"], alignment=TA_RIGHT,
    )
    styles["Cell"] = ParagraphStyle(
        "Cell", fontName=FONT, fontSize=8, leading=10.4, textColor=TEXT,
    )
    styles["CellMono"] = ParagraphStyle(
        "CellMono", parent=styles["Cell"], fontName=MONO, fontSize=7.2,
        textColor=MUTED,
    )
    styles["CellStrong"] = ParagraphStyle(
        "CellStrong", parent=styles["Cell"], fontName=FONT_BOLD, textColor=INK,
    )
    styles["CellRight"] = ParagraphStyle(
        "CellRight", parent=styles["CellStrong"], alignment=TA_RIGHT,
    )
    styles["KpiLabel"] = ParagraphStyle(
        "KpiLabel", fontName=FONT_BOLD, fontSize=6.6, leading=9,
        textColor=MUTED,
    )
    styles["KpiValue"] = ParagraphStyle(
        "KpiValue", fontName=FONT_BOLD, fontSize=13.5, leading=16,
        textColor=INK,
    )
    styles["HeroLabel"] = ParagraphStyle(
        "HeroLabel", fontName=FONT_BOLD, fontSize=6.4, leading=9,
        textColor=GOLD_LIGHT,
    )
    styles["HeroValue"] = ParagraphStyle(
        "HeroValue", fontName=MONO_BOLD, fontSize=14.5, leading=19,
        textColor=colors.white,
    )
    styles["TicketLabel"] = ParagraphStyle(
        "TicketLabel", fontName=FONT_BOLD, fontSize=6.2, leading=8.4,
        textColor=FAINT,
    )
    styles["TicketValue"] = ParagraphStyle(
        "TicketValue", fontName=MONO, fontSize=6.6, leading=8.8,
        textColor=MUTED,
    )
    styles["TicketSmall"] = ParagraphStyle(
        "TicketSmall", fontName=FONT, fontSize=6, leading=8.4,
        textColor=FAINT,
    )
    return styles


# ─────────────────────────────────────────────────────────────────────────────
# PAGE CHROME (banner, footer, page numbering)
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# BRANDING — drop your own emblem / coat of arms here
#   static/branding/emblem.png   (transparent PNG or JPG, square works best)
# The built-in gold monogram is used automatically while no file is present.
# ─────────────────────────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BRANDING_DIR = os.path.join(BASE_DIR, "static", "branding")
EMBLEM_FILE = os.path.join(BRANDING_DIR, "emblem.png")

_EMBLEM_CANDIDATES = ("emblem.png", "emblem.jpg", "emblem.jpeg", "emblem.webp",
                      "logo.png", "logo.jpg", "logo.jpeg", "logo.webp")


def find_emblem():
    """Return the path of the client-supplied emblem, or None."""
    if os.path.exists(EMBLEM_FILE):
        return EMBLEM_FILE
    for name in _EMBLEM_CANDIDATES:
        path = os.path.join(BRANDING_DIR, name)
        if os.path.exists(path):
            return path
    return None


def _draw_brand_mark(c, cx, cy, box_w, box_h):
    """Draw the supplied emblem inside the reserved slot; nothing is drawn otherwise."""
    path = find_emblem()
    if not path:
        return
    try:
        from reportlab.lib.utils import ImageReader

        img = ImageReader(path)
        iw, ih = img.getSize()
        if not iw or not ih:
            return
        ratio = min(box_w / float(iw), box_h / float(ih))
        w, h = iw * ratio, ih * ratio
        c.drawImage(img, cx - w / 2.0, cy - h / 2.0, w, h, mask="auto")
    except Exception:
        return


def _chrome_cover(c, doc, meta):
    """White page header with a reserved emblem area at the top right."""
    top = PAGE_H
    right = PAGE_W - MARGIN
    c.saveState()

    # Bank identity (left)
    c.setFillColor(GOLD)
    c.rect(MARGIN, top - 24, 26, 2.4, stroke=0, fill=1)
    c.setFillColor(INK)
    c.setFont(SERIF_BOLD, 19)
    c.drawString(MARGIN, top - 41, "AKUMA BANK")
    c.setFillColor(MUTED)
    c.setFont(FONT, 6.2)
    c.drawString(MARGIN, top - 54, "Agrément Bank Al-Maghrib n° BAM/2026/088   ·   "
                                   "Avenue Mohammed V — 10 000 Rabat")
    c.setFillColor(FAINT)
    c.setFont(FONT, 5.8)
    c.drawString(MARGIN, top - 65, "TÉL. +212 5 22 00 00 00   ·   SWIFT AKUMMAMCXXX   ·   WWW.AKUMABANK.MA")

    # Emblem slot — left empty on purpose, your crest goes here
    slot_w, slot_h = EMBLEM_SLOT
    _draw_brand_mark(c, right - slot_w / 2.0, top - 16 - slot_h / 2.0, slot_w, slot_h)

    # Reference line, right side under the emblem area
    c.setFillColor(FAINT)
    c.setFont(FONT_BOLD, 5.8)
    c.drawRightString(right, top - 88, "RÉFÉRENCE OFFICIELLE")
    c.setFillColor(NAVY)
    c.setFont(MONO_BOLD, 7.4)
    c.drawRightString(right, top - 98, meta["ref"])

    # Rules closing the header
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.2)
    c.line(MARGIN, top - 104, right, top - 104)
    c.setStrokeColor(LINE)
    c.setLineWidth(0.5)
    c.line(MARGIN, top - 106.5, right, top - 106.5)
    c.restoreState()


def _chrome_run(c, doc, meta):
    """Compact white header on every page after the first."""
    top = PAGE_H
    right = PAGE_W - MARGIN
    c.saveState()
    c.setFillColor(INK)
    c.setFont(SERIF_BOLD, 9)
    c.drawString(MARGIN, top - 25, "AKUMA BANK")
    c.setFillColor(FAINT)
    c.setFont(FONT, 6.4)
    name_w = pdfmetrics.stringWidth("AKUMA BANK", SERIF_BOLD, 9)
    c.drawString(MARGIN + name_w + 8, top - 25, f"·  {meta['short']}")
    c.setFillColor(MUTED)
    c.setFont(MONO, 6.6)
    c.drawRightString(right, top - 25, meta["ref"])
    c.setStrokeColor(LINE)
    c.setLineWidth(0.6)
    c.line(MARGIN, top - 32, right, top - 32)
    c.restoreState()


def _draw_footer(c, meta, page_no, total):
    """Footer: legal line, document identifier and page numbering."""
    c.saveState()
    c.setStrokeColor(LINE)
    c.setLineWidth(0.7)
    c.line(MARGIN, FOOTER_H - 6, PAGE_W - MARGIN, FOOTER_H - 6)

    c.setFillColor(MUTED)
    c.setFont(FONT, 6.3)
    c.drawString(MARGIN, FOOTER_H - 19,
                 "AKUMA BANK S.A. — Rabat, Maroc  ·  Agrément Bank Al-Maghrib n° BAM/2026/088")
    c.setFillColor(FAINT)
    c.setFont(FONT, 6.1)
    c.drawString(MARGIN, FOOTER_H - 29,
                 "Document généré et authentifié électroniquement — sans rature ni surcharge.")

    c.setFillColor(INK)
    c.setFont(FONT_BOLD, 7.2)
    c.drawRightString(PAGE_W - MARGIN, FOOTER_H - 19, f"Page {page_no} / {total}")
    c.setFillColor(FAINT)
    c.setFont(MONO, 6.1)
    c.drawRightString(PAGE_W - MARGIN, FOOTER_H - 29, meta["ref"])
    c.restoreState()


class _NumberedCanvas(_canvas.Canvas):
    """Two-pass canvas so the footer can print 'Page X / Y'."""

    def __init__(self, *args, **kwargs):
        _canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []
        self.bank_meta = {}

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            _draw_footer(self, self.bank_meta, self._pageNumber, total)
            _canvas.Canvas.showPage(self)
        _canvas.Canvas.save(self)


def _render(buf, story, meta):
    """Build a document with the shared page chrome and numbering."""
    cover_frame = Frame(
        MARGIN, FOOTER_H, CONTENT_W, COVER_TOP - FOOTER_H,
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="cover",
    )
    run_frame = Frame(
        MARGIN, FOOTER_H, CONTENT_W, RUN_TOP - FOOTER_H,
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="run",
    )
    doc = BaseDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=HEADER_H + 10, bottomMargin=FOOTER_H,
        title=meta["title"], author="Akuma Bank S.A.",
        subject=meta["short"], creator="Akuma Bank Document Engine",
    )
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[cover_frame],
                     onPage=lambda cnv, d: _chrome_cover(cnv, d, meta)),
        PageTemplate(id="run", frames=[run_frame],
                     onPage=lambda cnv, d: _chrome_run(cnv, d, meta)),
    ])
    story.insert(0, NextPageTemplate("run"))

    def maker(*args, **kwargs):
        cnv = _NumberedCanvas(*args, **kwargs)
        cnv.bank_meta = meta
        return cnv

    doc.build(story, canvasmaker=maker)


# ─────────────────────────────────────────────────────────────────────────────
# SHARED FLOWABLE BUILDERS
# ─────────────────────────────────────────────────────────────────────────────

def _v(value, default="—"):
    """Escape a data value for use inside ReportLab markup."""
    if value is None or value == "":
        return default
    return _escape(str(value))


def _money(value):
    try:
        return f"{float(value):,.2f}".replace(",", "\u202f")
    except (TypeError, ValueError):
        return "0.00"


def _title_block(styles, eyebrow, title, subtitle, items):
    """Eyebrow + serif title + bilingual subtitle + identification strip."""
    story = [Spacer(1, 2)]

    bar = Table([["", Paragraph(eyebrow, styles["Eyebrow"])]],
                colWidths=[3.2, CONTENT_W - 3.2])
    bar.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), GOLD),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 0),
        ("LEFTPADDING", (1, 0), (1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(bar)
    story.append(Paragraph(title, styles["DocTitle"]))
    if subtitle:
        story.append(Paragraph(subtitle, styles["DocSub"]))
    story.append(HRFlowable(width="100%", thickness=0.8, color=LINE,
                            spaceBefore=5, spaceAfter=6))

    if items:
        cells = []
        for label, value in items:
            cells.append([
                Paragraph(_escape(label.upper()), styles["MetaLabel"]),
                Paragraph(value, styles["MetaValue"]),
            ])
        strip = Table([cells], colWidths=[CONTENT_W / len(cells)] * len(cells))
        cmd = [
            ("BACKGROUND", (0, 0), (-1, -1), PANEL),
            ("BOX", (0, 0), (-1, -1), 0.6, LINE),
            ("LINEABOVE", (0, 0), (-1, 0), 1.6, GOLD),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 9),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]
        for i in range(1, len(cells)):
            cmd.append(("LINEBEFORE", (i, 0), (i, 0), 0.6, LINE))
        strip.setStyle(TableStyle(cmd))
        story.append(strip)
        story.append(Spacer(1, 10))

    return story


def _section(styles, number, title, note=None):
    """Numbered section heading with a gold-accented rule."""
    badge = Table([[Paragraph(str(number), styles["SectionBadge"])]], colWidths=[16], rowHeights=[16])
    badge.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), INK),
        ("BOX", (0, 0), (-1, -1), 0.7, GOLD),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    heading = [Paragraph(title.upper(), styles["SectionTitle"])]
    if note:
        heading.append(Paragraph(f"<font size=7 color='#94a3b8'>{note}</font>", styles["DocSub"]))
    row = Table([[badge, heading]], colWidths=[16 + 10, CONTENT_W - 26])
    row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -1), 0.6, LINE),
    ]))
    return [Spacer(1, 3), row, Spacer(1, 11)]


def _kv_table(styles, rows, label_w=142, value_style="KvValue", width=CONTENT_W):
    """Two-column information table: tinted label column, hairline rules."""
    data = []
    for label, value in rows:
        data.append([
            Paragraph(_escape(str(label).upper()), styles["KvLabel"]),
            Paragraph(value, styles[value_style]),
        ])
    t = Table(data, colWidths=[label_w, width - label_w])
    cmd = [
        ("BACKGROUND", (0, 0), (0, -1), PANEL),
        ("BACKGROUND", (1, 0), (1, -1), WHITE),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, LINE),
        ("LINEAFTER", (0, 0), (0, -1), 0.5, LINE),
    ]
    t.setStyle(TableStyle(cmd))
    return t


def _kv_pairs_table(styles, rows, label_w=112):
    """Four-column table presenting (label, value, label, value) pairs."""
    data = []
    for left, right in rows:
        data.append([
            Paragraph(_escape(left[0].upper()), styles["KvLabel"]),
            Paragraph(left[1], styles["KvValue"]),
            Paragraph(_escape(right[0].upper()), styles["KvLabel"]),
            Paragraph(right[1], styles["KvValue"]),
        ])
    widths = [label_w, (CONTENT_W - 2 * label_w) / 2, label_w, (CONTENT_W - 2 * label_w) / 2]
    t = Table(data, colWidths=widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), PANEL),
        ("BACKGROUND", (2, 0), (2, -1), PANEL),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, LINE),
        ("LINEAFTER", (0, 0), (0, -1), 0.5, LINE),
        ("LINEAFTER", (2, 0), (2, -1), 0.5, LINE),
    ]))
    return t


def _notice(styles, text, accent=GOLD, tint=PANEL):
    """Quiet legal / acknowledgement panel with a coloured edge."""
    t = Table([[Paragraph(text, styles["Legal"])]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), tint),
        ("LINEBEFORE", (0, 0), (0, -1), 2.2, accent),
        ("LEFTPADDING", (0, 0), (-1, -1), 13),
        ("RIGHTPADDING", (0, 0), (-1, -1), 13),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    return t


def _perks_table(styles, perks, columns=1):
    """Bulleted privilege list, optionally in two columns."""
    if columns == 2 and len(perks) > 3:
        half = (len(perks) + 1) // 2
        left = [Paragraph(_escape(p), styles["Perk"], bulletText="•") for p in perks[:half]]
        right = [Paragraph(_escape(p), styles["Perk"], bulletText="•") for p in perks[half:]]
        while len(right) < len(left):
            right.append(Paragraph("", styles["Perk"]))
        data = [[left[i], right[i]] for i in range(len(left))]
        t = Table(data, colWidths=[CONTENT_W / 2 - 6, CONTENT_W / 2 - 6])
    else:
        data = [[Paragraph(_escape(p), styles["Perk"], bulletText="•")] for p in perks]
        t = Table(data, colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def _metric_cards(styles, cards):
    """Row of KPI cards: [(label, value, colour), ...]."""
    gap = 9.0
    n = len(cards)
    card_w = (CONTENT_W - gap * (n - 1)) / n
    widths, cells, cmd = [], [], []
    for i, (label, value, colour) in enumerate(cards):
        cells.append([
            Paragraph(_escape(label.upper()), styles["KpiLabel"]),
            Spacer(1, 3),
            Paragraph(value, ParagraphStyle(
                f"Kpi{i}", parent=styles["KpiValue"], textColor=colour)),
        ])
        widths.append(card_w)
        cmd.extend([
            ("BACKGROUND", (i * 2, 0), (i * 2, 0), WHITE),
            ("BOX", (i * 2, 0), (i * 2, 0), 0.6, LINE),
            ("LINEABOVE", (i * 2, 0), (i * 2, 0), 2.2, colour),
            ("LEFTPADDING", (i * 2, 0), (i * 2, 0), 10),
            ("RIGHTPADDING", (i * 2, 0), (i * 2, 0), 8),
            ("TOPPADDING", (i * 2, 0), (i * 2, 0), 7),
            ("BOTTOMPADDING", (i * 2, 0), (i * 2, 0), 9),
        ])
        if i < n - 1:
            cells.append("")
            widths.append(gap)
    t = Table([cells], colWidths=widths)
    t.setStyle(TableStyle(cmd + [("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


# ─────────────────────────────────────────────────────────────────────────────
# ARTWORK: CARD, SEAL, STAMP
# ─────────────────────────────────────────────────────────────────────────────

TIER_PDF_STYLES = {
    "standard":  {"bg": "#0B1F3A", "accent": "#4E9BD8", "chip": "#C9A227", "name": "VISA CLASSIC"},
    "student":   {"bg": "#0B3F63", "accent": "#5CB6E8", "chip": "#C9A227", "name": "CAMPUS YOUTH"},
    "women":     {"bg": "#5C1130", "accent": "#E8A0B4", "chip": "#D9A3B5", "name": "SAYIDATI"},
    "gold":      {"bg": "#4A2B0C", "accent": "#E0B94E", "chip": "#D8B04A", "name": "GOLD PREMIER"},
    "platinum":  {"bg": "#1B2430", "accent": "#B9C4D1", "chip": "#9AA6B4", "name": "PLATINUM ELITE"},
    "infinite":  {"bg": "#08090C", "accent": "#DCC98A", "chip": "#C9B072", "name": "VISA INFINITE"},
    "business":  {"bg": "#101A2A", "accent": "#8FA3BC", "chip": "#7F8FA6", "name": "BUSINESS PRO"},
    "freelance": {"bg": "#2A1F1A", "accent": "#E09A54", "chip": "#C98A3E", "name": "SELF-EMPLOYED"},
    "travel":    {"bg": "#0A3A4C", "accent": "#4FC3B4", "chip": "#2FA795", "name": "WORLD TRAVEL"},
    "eco":       {"bg": "#0A3B2C", "accent": "#54C08C", "chip": "#3AA573", "name": "GREEN CARD"},
    "family":    {"bg": "#2A1244", "accent": "#AE8FD6", "chip": "#9573C4", "name": "FAMILY"},
}


def _arc(d, cx, cy, radius, start, extent, colour, width=1.3):
    """Draw a circular arc as a stroked polyline (Path has no arc primitive)."""
    steps = 26
    p = Path(strokeColor=colour, strokeWidth=width, fillColor=None,
             strokeLineCap=1, strokeLineJoin=1)
    for i in range(steps + 1):
        angle = math.radians(start + extent * i / steps)
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        if i == 0:
            p.moveTo(x, y)
        else:
            p.lineTo(x, y)
    d.add(p)


def _draw_visual_card(tier_id: str, card_number: str, holder_name: str,
                      expiry: str = "11/31", scale: float = 1.0):
    """Vector rendering of the subscribed card, matching the tier template."""
    cfg = TIER_PDF_STYLES.get(tier_id, TIER_PDF_STYLES["standard"])
    bg = colors.HexColor(cfg["bg"])
    accent = colors.HexColor(cfg["accent"])
    chip = colors.HexColor(cfg["chip"])
    badge_label = cfg["name"]

    w, h = 286, 170
    d = Group()
    radius = 11

    # Card body
    d.add(Rect(0, 0, w, h, rx=radius, ry=radius, fillColor=bg, strokeColor=None))

    # Very light horizontal guilloche lines (kept clear of the rounded corners)
    for i in range(12, int(h) - 11, 5):
        d.add(Line(1, i, w - 1, i,
                   strokeColor=colors.Color(1, 1, 1, alpha=0.035), strokeWidth=0.5))

    # Soft highlight sweep across the upper half
    d.add(Rect(1, h * 0.52, w - 2, h * 0.46, rx=0, ry=0,
               fillColor=colors.Color(1, 1, 1, alpha=0.03), strokeColor=None))

    # Inner accent frame
    d.add(Rect(6, 6, w - 12, h - 12, rx=7, ry=7,
               fillColor=None, strokeColor=colors.Color(accent.red, accent.green, accent.blue, alpha=0.45),
               strokeWidth=0.6))

    # Wordmark
    d.add(String(20, h - 30, "AKUMA BANK", fontName=SERIF_BOLD, fontSize=11.5, fillColor=colors.white))
    d.add(String(20, h - 38.5, "BANK AL-MAGHRIB CERTIFIED", fontName=FONT, fontSize=4.9,
                 fillColor=colors.Color(1, 1, 1, alpha=0.55)))

    # Tier badge
    badge_w = pdfmetrics.stringWidth(badge_label, FONT_BOLD, 6.6) + 16
    d.add(Rect(w - badge_w - 16, h - 33, badge_w, 14, rx=7, ry=7, fillColor=accent, strokeColor=None))
    d.add(String(w - badge_w - 16 + 8, h - 28.4, badge_label,
                 fontName=FONT_BOLD, fontSize=6.6, fillColor=bg))

    # EMV chip
    chip_x, chip_y, chip_w, chip_h = 20, 88, 36, 27
    d.add(Rect(chip_x, chip_y, chip_w, chip_h, rx=4, ry=4, fillColor=chip, strokeColor=None))
    d.add(Rect(chip_x, chip_y, chip_w, chip_h, rx=4, ry=4, fillColor=None,
               strokeColor=colors.Color(0, 0, 0, alpha=0.28), strokeWidth=0.5))
    for frac in (0.28, 0.5, 0.72):
        d.add(Line(chip_x + 4, chip_y + chip_h * frac, chip_x + chip_w - 4, chip_y + chip_h * frac,
                   strokeColor=colors.Color(0, 0, 0, alpha=0.22), strokeWidth=0.6))
    d.add(Line(chip_x + chip_w / 2, chip_y + 3, chip_x + chip_w / 2, chip_y + chip_h - 3,
               strokeColor=colors.Color(0, 0, 0, alpha=0.22), strokeWidth=0.6))

    # Contactless arcs
    for i, r in enumerate((4.5, 8.5, 12.5)):
        _arc(d, chip_x + chip_w + 12, chip_y + chip_h / 2, r, -52, 104, accent, 1.1)

    # Card number
    masked = format_card_number(card_number, masked=True)
    d.add(String(20, 54, masked, fontName=MONO_BOLD, fontSize=12.6,
                 fillColor=colors.Color(1, 1, 1, alpha=0.97)))

    # Labels
    d.add(String(20, 30, "TITULAIRE / CARDHOLDER", fontName=FONT_BOLD, fontSize=4.4,
                 fillColor=colors.Color(1, 1, 1, alpha=0.42)))
    clean_name = (holder_name or "VALUED CLIENT").upper()[:26]
    d.add(String(20, 19, clean_name, fontName=FONT_BOLD, fontSize=8.4, fillColor=colors.white))

    d.add(String(168, 30, "VALABLE JUSQU'AU", fontName=FONT_BOLD, fontSize=4.4,
                 fillColor=colors.Color(1, 1, 1, alpha=0.42)))
    d.add(String(168, 19, expiry, fontName=MONO_BOLD, fontSize=8.4, fillColor=colors.white))

    # Brand mark
    d.add(String(w - 62, 17, "VISA", fontName=SERIF_BOLD_ITALIC, fontSize=13.5,
                 fillColor=colors.Color(1, 1, 1, alpha=0.95)))
    d.add(String(w - 63, 30, "PLATINUM" if tier_id in ("platinum", "infinite") else "DEBIT",
                 fontName=FONT_BOLD, fontSize=4.4, fillColor=colors.Color(1, 1, 1, alpha=0.45)))

    out = Drawing(w * scale, h * scale)
    d.transform = (scale, 0, 0, scale, 0, 0)
    out.add(d)
    return out


def _status_stamp(label, sublabel, tone, width=186, height=92):
    """Right-aligned official status stamp (used on the closure certificate)."""
    d = Drawing(width, height)
    d.add(_status_stamp_group(label, sublabel, tone, width / 2.0 - 4, height / 2.0, scale=0.86))
    d.hAlign = "RIGHT"
    return d


def _status_stamp_group(label, sublabel, tone, cx, cy, scale=1.0):
    """Rotated official stamp (group) centred on (cx, cy)."""
    g = Group()
    angle = math.radians(7)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    g.transform = (scale * cos_a, scale * sin_a, -scale * sin_a, scale * cos_a, cx, cy)

    g.add(Rect(-84, -30, 168, 60, rx=4, ry=4,
               fillColor=colors.Color(1, 1, 1, alpha=0.82), strokeColor=None))
    g.add(Rect(-84, -30, 168, 60, rx=4, ry=4, fillColor=None, strokeColor=tone, strokeWidth=2))
    g.add(Rect(-80, -25, 160, 50, rx=3, ry=3, fillColor=None, strokeColor=tone, strokeWidth=0.6))
    g.add(String(-80, 4, label, fontName=FONT_BOLD, fontSize=14, fillColor=tone))
    g.add(String(-80, -8, sublabel, fontName=FONT_BOLD, fontSize=5.9, fillColor=tone))
    g.add(String(-80, -18, datetime.now().strftime("%d/%m/%Y"), fontName=MONO, fontSize=5.8,
                 fillColor=tone))
    return g


# ─────────────────────────────────────────────────────────────────────────────
# 1. ACCOUNT OPENING CERTIFICATE & WELCOME PACK (WITH CARD TEMPLATE)
# ─────────────────────────────────────────────────────────────────────────────

def generate_opening_certificate_pdf(account: dict, customer: dict, branch: dict, tier: dict) -> BytesIO:
    """Generate official Welcome Pack & Account Opening Certificate."""
    buf = BytesIO()
    styles = _get_styles()
    story = []

    account_id = account.get("AccountID", 0)
    now = datetime.now()
    meta = {
        "ref": f"AKM-OPN-{account_id:05d}-{now.strftime('%Y%m%d')}",
        "date": now.strftime("%d/%m/%Y à %H:%M"),
        "short": "Attestation d'ouverture de compte & Welcome Pack",
        "title": "Account Opening Certificate & Welcome Pack",
    }

    iban = rib_to_iban(account.get("AccountNumber", ""))
    story.extend(_title_block(
        styles,
        "ATTESTATION OFFICIELLE · OUVERTURE DE COMPTE",
        "Attestation d'Ouverture de Compte<br/>& Welcome Pack",
        "Attestation officielle d'ouverture de compte et remise de carte bancaire",
        [
            ("Titulaire", _v(customer.get("Name"))),
            ("Agence", f"{_v(branch.get('BranchName', 'Agence Centrale'))}"),
            ("Date d'ouverture", _v(account.get("OpeningDate", now.strftime("%Y-%m-%d")))),
        ],
    ))

    # 1. Account holder & identification
    story.extend(_section(styles, 1, "Titulaire du compte & identification", "Account holder details"))
    story.append(_kv_pairs_table(styles, [
        (("Nom complet", _v(customer.get("Name"))),
         ("CIN", _v(customer.get("NationalID")))),
        (("E-mail", _v(customer.get("Email"))),
         ("Téléphone", _v(customer.get("Phone")))),
        (("Adresse", _v(customer.get("Address"))),
         ("Solde d'ouverture", f"<font face='{FONT_BOLD}' color='#0B1F3A'>MAD {_money(account.get('Balance', 0))}</font>")),
        (("N° de compte", f"<font face='{MONO_BOLD}' color='#0B1F3A'>{_v(account.get('AccountNumber'))}</font>"),
         ("Type de compte", _v(account.get("AccountType", "Current")))),
        (("RIB (24 chiffres)", f"<font face='{MONO_BOLD}' size=7.6>{format_moroccan_rib(account.get('AccountNumber', ''))}</font>"),
         ("IBAN", f"<font face='{MONO}' size=7.6>{format_iban(iban)}</font>")),
    ], label_w=98))

    story.append(Spacer(1, 9))

    # 2. Card subscription with visual card
    story.extend(_section(styles, 2, "Carte bancaire souscrite", "Debit card issued with the account"))
    card_scale = 0.82
    card_w = 286 * card_scale
    card_drawing = _draw_visual_card(
        tier_id=tier.get("id", "standard"),
        card_number=account.get("CardNumber", "4240123456789012"),
        holder_name=customer.get("Name", "VALUED CLIENT"),
        scale=card_scale,
    )
    card_block = Table([[
        card_drawing,
        [
            Paragraph("PRODUIT SOUSCRIT", styles["KvLabel"]),
            Paragraph(f"<font face='{FONT_BOLD}' size=10.2 color='#0B1F3A'>{_v(tier.get('name', 'Essential Pack'))}</font>",
                      styles["KvValue"]),
            Spacer(1, 6),
            _kv_table(styles, [
                ("Catégorie", f"{_v(tier.get('category', 'Personal'))} · {_v(tier.get('badge', 'VISA'))}"),
                ("Cotisation", f"<font face='{FONT_BOLD}'>{_v(tier.get('monthly_fee', '0 MAD / month'))}</font>"),
                ("Plafond du compte", f"<font face='{FONT_BOLD}'>{_v(tier.get('plafond', '100,000 MAD'))}</font>"),
                ("Numéro de carte", f"<font face='{MONO_BOLD}'>"
                                    f"{format_card_number(account.get('CardNumber', ''), masked=True)}</font>"),
            ], label_w=88, width=CONTENT_W - card_w - 16),
        ],
    ]], colWidths=[card_w + 16, CONTENT_W - card_w - 16])
    card_block.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(card_block)

    story.append(Spacer(1, 10))
    perks = tier.get("perks") or [
        "Retraits DAB et paiements TPE acceptés dans tout le Royaume",
        "Conformité interbancaire Bank Al-Maghrib",
        "Assistance carte 24/7 et prévention de la fraude",
    ]
    story.append(_perks_table(styles, perks, columns=2))

    story.append(Spacer(1, 8))

    # 3. Regulatory acknowledgement
    story.extend(_section(styles, 3, "Cadre réglementaire & acceptation", "Regulatory acknowledgement"))
    story.append(_notice(
        styles,
        "Le présent compte est régi par la loi marocaine n° 103-12 et par les circulaires de Bank Al-Maghrib. "
        "Le RIB à 24 chiffres respecte le standard Modulo 97 et l'IBAN la norme ISO 13616. Le titulaire certifie "
        "l'exactitude des informations communiquées et reconnaît avoir reçu les conditions générales du compte.",
    ))

    story.append(Spacer(1, 6))

    _render(buf, story, meta)
    buf.seek(0)
    return buf


# ─────────────────────────────────────────────────────────────────────────────
# 2. ACCOUNT CLOSURE CERTIFICATE & DISCHARGE (ATTESTATION DE CLÔTURE ET QUITTUS)
# ─────────────────────────────────────────────────────────────────────────────

def generate_closure_certificate_pdf(account: dict, customer: dict, branch: dict, reason: str = None) -> BytesIO:
    """Generate official Account Closure Certificate & Quittus."""
    buf = BytesIO()
    styles = _get_styles()
    story = []

    account_id = account.get("AccountID", 0)
    now = datetime.now()
    meta = {
        "ref": f"AKM-CLS-{account_id:05d}-{now.strftime('%Y%m%d')}",
        "date": now.strftime("%d/%m/%Y à %H:%M"),
        "short": "Attestation de clôture de compte & quittus définitif",
        "title": "Certificate of Account Closure & Discharge",
    }

    story.extend(_title_block(
        styles,
        "ATTESTATION OFFICIELLE · CLÔTURE DÉFINITIVE",
        "Attestation de Clôture de Compte<br/>& Quittus Définitif",
        "Certificat officiel de fermeture de compte et de libération réciproque des engagements",
        [
            ("Titulaire", _v(customer.get("Name"))),
            ("Compte clôturé le", now.strftime("%d/%m/%Y")),
            ("Statut", "CLÔTURÉ — SOLDÉ"),
        ],
    ))

    statement = (
        f"<b>Akuma Bank S.A.</b> atteste par la présente que le compte bancaire désigné ci-dessous, ouvert dans "
        f"nos livres au nom de <b>{_v(customer.get('Name'))}</b>, a été <b>définitivement clôturé et liquidé</b> "
        f"à la date du <b>{now.strftime('%d/%m/%Y')}</b>, conformément à la réglementation bancaire marocaine "
        f"en vigueur et aux conditions générales acceptées par le titulaire."
    )
    story.append(_notice(styles, statement, accent=NAVY, tint=WHITE))
    story.append(Spacer(1, 12))

    story.extend(_section(styles, 1, "Compte & liquidation", "Account and liquidation details"))
    details = _kv_table(styles, [
        ("Titulaire du compte", f"<font face='{FONT_BOLD}'>{_v(customer.get('Name'))}</font>"),
        ("CIN / Passeport", _v(customer.get("NationalID"))),
        ("Numéro de compte", f"<font face='{MONO_BOLD}'>{_v(account.get('AccountNumber'))}</font>"),
        ("RIB marocain", f"<font face='{MONO_BOLD}'>{format_moroccan_rib(account.get('AccountNumber', ''))}</font>"),
        ("Agence gestionnaire", f"{_v(branch.get('BranchName', 'Agence Centrale'))} — {_v(branch.get('City', 'Rabat'))}"),
        ("Date de clôture", now.strftime("%d/%m/%Y à %H:%M")),
        ("Motif de clôture", _v(reason or "Demande du client / accord mutuel")),
        ("Solde final", f"<font color='#12715A'><b>MAD 0,00 — soldé intégralement</b></font>"),
        ("Instruments de paiement liés", f"<font color='#A32020'><b>Désactivés et annulés définitivement</b></font>"),
    ], label_w=170)
    story.append(details)

    story.append(Spacer(1, 6))
    story.append(_status_stamp("CLÔTURÉ", "ACCOUNT CLOSED — DISCHARGED", RED))
    story.append(Spacer(1, 4))

    story.extend(_section(styles, 2, "Quittus & libération des engagements", "Release of reciprocal commitments"))
    story.append(_notice(
        styles,
        "Akuma Bank S.A. confirme qu'à compter de cette date, l'ensemble des moyens de paiement rattachés à ce "
        "compte (carte bancaire, chéquiers, prélèvements et virements permanents) ont été rendus nuls et non "
        "avenus. Le titulaire est formellement déchargé de toute cotisation de tenue de compte ou commission "
        "ultérieure. Réciproquement, la banque reconnaît que toutes les opérations en instance ont été traitées "
        "et réglées. Le présent certificat est délivré pour servir et valoir ce que de droit.",
    ))

    story.append(Spacer(1, 12))

    _render(buf, story, meta)
    buf.seek(0)
    return buf


# ─────────────────────────────────────────────────────────────────────────────
# 3. CARD SUBSCRIPTION CERTIFICATE & SPECIFICATION SHEET
# ─────────────────────────────────────────────────────────────────────────────

def generate_card_subscription_pdf(account: dict, customer: dict, tier: dict) -> BytesIO:
    """Generate detailed Card Subscription & Specification Document."""
    buf = BytesIO()
    styles = _get_styles()
    story = []

    account_id = account.get("AccountID", 0)
    now = datetime.now()
    meta = {
        "ref": f"AKM-CRD-{account_id:05d}-{now.strftime('%Y%m%d')}",
        "date": now.strftime("%d/%m/%Y à %H:%M"),
        "short": "Attestation de carte bancaire & conditions de souscription",
        "title": "Card Subscription Attestation & Specifications",
    }

    story.extend(_title_block(
        styles,
        "ATTESTATION OFFICIELLE · CARTE BANCAIRE",
        "Attestation de Carte Bancaire<br/>& Spécifications Techniques",
        "Attestation de souscription et conditions de fonctionnement de la carte",
        [
            ("Produit", _v(tier.get("name", "N/A"))),
            ("Titulaire", _v(customer.get("Name"))),
            ("Compte rattaché", _v(account.get("AccountNumber"))),
        ],
    ))

    # 1. Card visual
    story.extend(_section(styles, 1, "Visuel de la carte & identification", "Card visual template"))
    card_scale = 0.82
    card_w = 286 * card_scale
    card_drawing = _draw_visual_card(
        tier_id=tier.get("id", "standard"),
        card_number=account.get("CardNumber", "4240123456789012"),
        holder_name=customer.get("Name", "VALUED CLIENT"),
        scale=card_scale,
    )
    tier_facts = Table([[
        [Paragraph("POSITIONNEMENT", styles["KvLabel"]),
         Paragraph(_v(tier.get("tagline", "Carte de paiement et de retrait")), styles["KvValue"]),
         Spacer(1, 7),
         Paragraph("PLAFOND DU COMPTE", styles["KvLabel"]),
         Paragraph(f"<font face='{FONT_BOLD}' size=10 color='#0B1F3A'>{_v(tier.get('plafond', 'N/A'))}</font>",
                   styles["KvValue"]),
         Spacer(1, 7),
         Paragraph("COTISATION MENSUELLE", styles["KvLabel"]),
         Paragraph(f"<font face='{FONT_BOLD}' size=10 color='#0B1F3A'>{_v(tier.get('monthly_fee', '0 MAD / month'))}</font>",
                   styles["KvValue"])]
    ]], colWidths=[CONTENT_W - card_w - 16])
    tier_facts.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PANEL),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))

    hero = Table([[card_drawing, tier_facts]], colWidths=[card_w + 16, CONTENT_W - card_w - 16])
    hero.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(KeepTogether([hero]))

    story.append(Spacer(1, 8))

    # 2. Technical specifications
    story.extend(_section(styles, 2, "Spécifications techniques & financières", "Technical and financial terms"))
    story.append(_kv_table(styles, [
        ("Classification", f"{_v(tier.get('category', 'Personal'))} · Réseau {_v(tier.get('badge', 'VISA'))}"),
        ("Numéro de carte (masqué)",
         f"<font face='{MONO_BOLD}'>{format_card_number(account.get('CardNumber', ''), masked=True)}</font>"),
        ("RIB associé", f"<font face='{MONO_BOLD}'>{format_moroccan_rib(account.get('AccountNumber', ''))}</font>"),
        ("Paiement sans contact (NFC)", "Activé — jusqu'à 600 MAD sans saisie du code, conforme aux règles BAM"),
        ("Retraits et paiements", "Acceptés sur l'ensemble du réseau interbancaire marocain et à l'international"),
        ("Assistance carte 24/7", f"<b>+212 (0) 5 22 00 00 00</b> — mise en opposition instantanée"),
    ], label_w=178))

    story.append(Spacer(1, 8))

    # 3. Benefits
    story.extend(_section(styles, 3, "Avantages, assurances & privilèges", "Benefits included"))
    perks = tier.get("perks") or [
        "Retraits DAB et paiements TPE acceptés dans tout le Royaume",
        "Conformité interbancaire Bank Al-Maghrib",
        "Assistance carte 24/7 et prévention de la fraude",
    ]
    story.append(_perks_table(styles, perks, columns=2))

    story.append(Spacer(1, 8))
    story.append(_notice(
        styles,
        "La carte est strictement personnelle et incessible. Le titulaire s'engage à signaler sans délai toute "
        "perte, vol ou usage frauduleux auprès de l'assistance 24/7. Plafonds et cotisations sont ceux du barème "
        "en vigueur au jour de l'émission.",
    ))

    story.append(Spacer(1, 14))

    _render(buf, story, meta)
    buf.seek(0)
    return buf


# ─────────────────────────────────────────────────────────────────────────────
# 4. OFFICIAL 24-DIGIT MOROCCAN RIB ATTESTATION
# ─────────────────────────────────────────────────────────────────────────────

def generate_rib_attestation_pdf(account: dict, customer: dict, branch: dict) -> BytesIO:
    """Generate official Relevé d'Identité Bancaire (RIB) certificate."""
    buf = BytesIO()
    styles = _get_styles()
    story = []

    account_id = account.get("AccountID", 0)
    now = datetime.now()
    meta = {
        "ref": f"AKM-RIB-{account_id:05d}-{now.strftime('%Y%m%d')}",
        "date": now.strftime("%d/%m/%Y à %H:%M"),
        "short": "Relevé d'identité bancaire (RIB)",
        "title": "Relevé d'Identité Bancaire",
    }

    story.extend(_title_block(
        styles,
        "ATTESTATION BANCAIRE OFFICIELLE · RIB",
        "Relevé d'Identité Bancaire (RIB)",
        "Attestation officielle d'identité bancaire et de domiciliation — Modulo 97 / ISO 13616",
        [
            ("Titulaire", _v(customer.get("Name"))),
            ("Banque", "AKUMA BANK S.A. — Rabat"),
            ("Devise", "Dirham marocain (MAD)"),
        ],
    ))

    rib_str = account.get("AccountNumber", "")
    iban_str = rib_to_iban(rib_str)

    bank_code = rib_str[:3] if len(rib_str) >= 3 else "240"
    branch_code = rib_str[3:6] if len(rib_str) >= 6 else "810"
    account_seq = rib_str[6:22] if len(rib_str) >= 22 else "0" * 16
    key_code = rib_str[22:24] if len(rib_str) >= 24 else "00"

    # Hero panel
    hero_rows = [
        [Paragraph("IBAN — IDENTIFIANT INTERNATIONAL (ISO 13616)", styles["HeroLabel"])],
        [Paragraph(f"<font face='{MONO_BOLD}' size=13.2 color='#FFFFFF'>"
                   f"{format_iban(iban_str)}</font>", styles["HeroValue"])],
        [Paragraph("&nbsp;", styles["HeroLabel"])],
        [Paragraph("RIB — RELEVÉ D'IDENTITÉ BANCAIRE (24 CHIFFRES, MODULO 97)", styles["HeroLabel"])],
        [Paragraph(f"<font face='{MONO_BOLD}' size=15.4 color='#FFFFFF'>"
                   f"{format_moroccan_rib(rib_str)}</font>", styles["HeroValue"])],
    ]
    hero = Table(hero_rows, colWidths=[CONTENT_W])
    hero.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), INK),
        ("LINEABOVE", (0, 0), (-1, 0), 2.2, GOLD),
        ("LINEBELOW", (0, -1), (-1, -1), 2.2, GOLD),
        ("LEFTPADDING", (0, 0), (-1, -1), 18),
        ("RIGHTPADDING", (0, 0), (-1, -1), 18),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, 0), 14),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 16),
        ("LINEBELOW", (0, 1), (-1, 1), 0.4, colors.Color(GOLD.red, GOLD.green, GOLD.blue, alpha=0.5)),
    ]))
    story.append(hero)
    story.append(Spacer(1, 12))

    # RIB breakdown
    breakdown = [
        [Paragraph("CODE BANQUE<br/><font size=6 color='#64748b'>Bank code</font>", styles["KvLabel"]),
         Paragraph("CODE GUICHET<br/><font size=6 color='#64748b'>Branch code</font>", styles["KvLabel"]),
         Paragraph("NUMÉRO DE COMPTE<br/><font size=6 color='#64748b'>Account number (16 digits)</font>", styles["KvLabel"]),
         Paragraph("CLÉ RIB<br/><font size=6 color='#64748b'>Check key (Modulo 97)</font>", styles["KvLabel"])],
        [Paragraph(f"<font face='{MONO_BOLD}' size=14 color='#0B1F3A'>{bank_code}</font>", styles["KvValue"]),
         Paragraph(f"<font face='{MONO_BOLD}' size=14 color='#0B1F3A'>{branch_code}</font>", styles["KvValue"]),
         Paragraph(f"<font face='{MONO_BOLD}' size=14 color='#0B1F3A'>{account_seq}</font>", styles["KvValue"]),
         Paragraph(f"<font face='{MONO_BOLD}' size=14 color='#B8893B'>{key_code}</font>", styles["KvValue"])],
    ]
    t_rib = Table(breakdown, colWidths=[88, 88, CONTENT_W - 88 * 2 - 92, 92])
    t_rib.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PANEL),
        ("BACKGROUND", (0, 1), (-1, 1), WHITE),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.6, LINE),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(t_rib)
    story.append(Spacer(1, 14))

    # Holder and domiciliation
    story.extend(_section(styles, 1, "Titulaire & domiciliation bancaire", "Account holder and domiciliation"))
    story.append(_kv_pairs_table(styles, [
        (("Titulaire du compte", f"<font face='{FONT_BOLD}'>{_v(customer.get('Name'))}</font>"),
         ("Identifiant national (CIN)", _v(customer.get("NationalID")))),
        (("Adresse", _v(customer.get("Address"))),
         ("Ville", _v(branch.get("City", "Rabat")))),
        (("Banque domiciliataire", "AKUMA BANK S.A."),
         ("Agence / Branch", _v(branch.get("BranchName", "Agence Centrale")))),
        (("Code SWIFT / BIC", f"<font face='{MONO_BOLD}'>AKUMMAMCXXX</font>"),
         ("Nature du compte", f"Compte {_v(account.get('AccountType', 'Current'))} en dirhams (MAD)")),
    ]))

    story.append(Spacer(1, 14))
    story.append(_notice(
        styles,
        "Le présent Relevé d'Identité Bancaire est délivré pour servir et valoir ce que de droit, notamment pour "
        "la mise en place de virements (salaires, remboursements, prestations sociales) et de prélèvements "
        "automatiques. Les informations ci-dessus peuvent être communiquées au tiers bénéficiaire à cette seule fin.",
    ))

    story.append(Spacer(1, 16))

    _render(buf, story, meta)
    buf.seek(0)
    return buf


# ─────────────────────────────────────────────────────────────────────────────
# 5. ACCOUNT STATEMENT & ACTIVITY LOG (RELEVÉ BANCAIRE)
# ─────────────────────────────────────────────────────────────────────────────

def generate_statement_pdf(account: dict, customer: dict, branch: dict, transactions: list) -> BytesIO:
    """Generate official Account Statement & Activity Log."""
    buf = BytesIO()
    styles = _get_styles()
    story = []

    account_id = account.get("AccountID", 0)
    now = datetime.now()
    meta = {
        "ref": f"AKM-STM-{account_id:05d}-{now.strftime('%Y%m%d')}",
        "date": now.strftime("%d/%m/%Y à %H:%M"),
        "short": "Relevé de compte & historique des transactions",
        "title": "Account Statement & Activity Log",
    }

    rows_tx = transactions or []
    balance = float(account.get("Balance", 0.0) or 0)
    credits = sum(float(t.get("Amount", 0) or 0) for t in rows_tx
                  if t.get("TransactionType") == "Deposit")
    debits = sum(float(t.get("Amount", 0) or 0) for t in rows_tx
                 if t.get("TransactionType") in ("Withdrawal", "Transfer"))
    opening = balance - credits + debits

    dates = sorted({str(t.get("TransactionDate", ""))[:10] for t in rows_tx if t.get("TransactionDate")})
    period = f"du {dates[0]} au {dates[-1]}" if len(dates) > 1 else "période courante"

    story.extend(_title_block(
        styles,
        "RELEVÉ OFFICIEL · COMPTE COURANT",
        "Relevé de Compte<br/>& Historique des Opérations",
        "Relevé officiel de compte certifié conforme aux écritures comptables",
        [
            ("Titulaire", _v(customer.get("Name"))),
            ("Compte", f"<font face='{MONO_BOLD}' size=7.8>{_v(account.get('AccountNumber'))}</font>"),
            ("Période", period),
        ],
    ))

    story.append(Spacer(1, 4))
    story.append(_metric_cards(styles, [
        ("Solde actuel", f"MAD {_money(balance)}", INK),
        ("Total crédits", f"+ {_money(credits)}", GREEN),
        ("Total débits", f"\u2212 {_money(debits)}", RED),
    ]))
    story.append(Spacer(1, 12))

    story.append(_kv_table(styles, [
        ("Compte / IBAN", f"<font face='{MONO_BOLD}'>{format_iban(rib_to_iban(account.get('AccountNumber', '')))}</font>"),
        ("RIB marocain", f"<font face='{MONO_BOLD}'>{format_moroccan_rib(account.get('AccountNumber', ''))}</font>"),
        ("Agence de tenue", f"{_v(branch.get('BranchName', 'Agence Centrale'))} — {_v(branch.get('City', 'Rabat'))}"),
        ("Solde d'ouverture de période", f"MAD {_money(opening)}"),
        ("Nombre d'opérations", f"{len(rows_tx)} opération(s) enregistrée(s)"),
    ], label_w=178, value_style="KvValue"))

    story.append(Spacer(1, 14))

    # Transactions ledger
    story.extend(_section(styles, 1, "Détail des opérations", f"{len(rows_tx)} opérations"))
    header = [
        Paragraph("DATE / HEURE", styles["TableHead"]),
        Paragraph("TYPE", styles["TableHead"]),
        Paragraph("LIBELLÉ", styles["TableHead"]),
        Paragraph("MONTANT (MAD)", styles["TableHeadRight"]),
        Paragraph("SOLDE (MAD)", styles["TableHeadRight"]),
    ]
    data = [header]
    for tx in rows_tx:
        t_type = tx.get("TransactionType", "N/A")
        amt = float(tx.get("Amount", 0) or 0)
        bal = float(tx.get("BalanceAfter", 0) or 0)
        is_credit = t_type == "Deposit"
        amt_str = f"{'+' if is_credit else '\u2212'} {_money(amt)}"
        amt_color = "#12715A" if is_credit else "#A32020"
        label = {
            "Deposit": "Dépôt / Credit",
            "Withdrawal": "Retrait / Debit",
            "Transfer": "Virement / Transfer",
        }.get(t_type, t_type)
        data.append([
            Paragraph(str(tx.get("TransactionDate", ""))[:16], styles["CellMono"]),
            Paragraph(_escape(str(label)), styles["Cell"]),
            Paragraph(_v(tx.get("Description", "—")), styles["Cell"]),
            Paragraph(f"<font color='{amt_color}'>{amt_str}</font>", styles["CellRight"]),
            Paragraph(_money(bal), styles["CellRight"]),
        ])

    if len(data) == 1:
        data.append([
            Paragraph("Aucune opération enregistrée sur la période.", styles["Cell"]),
            "", "", "", "",
        ])

    t_tx = Table(data, colWidths=[92, 92, CONTENT_W - 92 - 92 - 76 - 76, 76, 76], repeatRows=1)
    cmd = [
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, 0), 7),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 0), (-1, 0), 1.1, GOLD),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            cmd.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F7F9FC")))
    t_tx.setStyle(TableStyle(cmd))
    story.append(t_tx)

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Ce relevé bancaire est certifié conforme aux écritures comptables enregistrées dans le système central "
        "d'Akuma Bank. Les opérations y figurant sont classées de la plus récente à la plus ancienne. "
        "Toute contestation doit être formulée dans les trente (30) jours suivant la date d'émission du présent relevé.",
        styles["Legal"],
    ))

    story.append(Spacer(1, 14))

    _render(buf, story, meta)
    buf.seek(0)
    return buf


# ─────────────────────────────────────────────────────────────────────────────
# 6. ATTESTATION DE SOLVABILITÉ ET DE CAPACITÉ FINANCIÈRE
# ─────────────────────────────────────────────────────────────────────────────

def generate_solvency_certificate_pdf(account: dict, customer: dict, branch: dict, purpose: str = None) -> BytesIO:
    """Generate official Bank Solvency & Good Standing Certificate."""
    buf = BytesIO()
    styles = _get_styles()
    story = []

    account_id = account.get("AccountID", 0)
    now = datetime.now()
    meta = {
        "ref": f"AKM-SOL-{account_id:05d}-{now.strftime('%Y%m%d')}",
        "date": now.strftime("%d/%m/%Y à %H:%M"),
        "short": "Attestation de solvabilité et de capacité financière",
        "title": "Attestation de Solvabilité",
    }

    dest_purpose = purpose or "Demande de visa / formalités administratives"

    story.extend(_title_block(
        styles,
        "ATTESTATION OFFICIELLE · SOLVABILITÉ",
        "Attestation de Solvabilité<br/>& de Capacité Financière",
        "Certificat officiel de bonne tenue de compte et de capacité financière",
        [
            ("Titulaire", _v(customer.get("Name"))),
            ("Objet", _v(dest_purpose)),
            ("Agence", _v(branch.get("BranchName", "Agence Centrale"))),
        ],
    ))

    statement = (
        f"La Direction d'<b>Akuma Bank S.A.</b> certifie par la présente que "
        f"<b>{_v(customer.get('Name'))}</b>, titulaire de la carte d'identité nationale / passeport "
        f"n° <b>{_v(customer.get('NationalID'))}</b>, est titulaire dans nos livres du compte bancaire "
        f"désigné ci-après et dont la situation est régulière."
    )
    story.append(_notice(styles, statement, accent=NAVY, tint=WHITE))
    story.append(Spacer(1, 12))

    story.extend(_section(styles, 1, "Identification du compte", "Account identification"))
    story.append(_kv_table(styles, [
        ("Titulaire du compte", f"<font face='{FONT_BOLD}'>{_v(customer.get('Name'))}</font>"),
        ("Identifiant national (CIN)", _v(customer.get("NationalID"))),
        ("Numéro de compte / RIB",
         f"<font face='{MONO_BOLD}'>{format_moroccan_rib(account.get('AccountNumber', ''))}</font>"),
        ("Nature du compte", f"Compte {_v(account.get('AccountType', 'Current'))} en dirhams (MAD)"),
        ("Date d'ouverture", _v(account.get("OpeningDate", "—"))),
        ("Agence gestionnaire", f"{_v(branch.get('BranchName', 'Agence Principale'))} — {_v(branch.get('City', 'Rabat'))}"),
        ("Objet / destination", f"<font face='{FONT_BOLD}'>{_v(dest_purpose)}</font>"),
    ], label_w=170))

    story.append(Spacer(1, 8))
    story.append(_metric_cards(styles, [
        ("Solde certifié", f"MAD {_money(account.get('Balance', 0))}", INK),
        ("Situation du compte", "Actif", GREEN),
        ("Incidents de paiement", "Aucun", GREEN),
    ]))

    story.append(Spacer(1, 14))

    story.extend(_section(styles, 2, "Déclarations de la banque", "Bank representations"))
    story.append(_perks_table(styles, [
        "Le compte fonctionne à notre entière satisfaction, sans incident de paiement ni opposition.",
        "Aucun découvert non autorisé ni impayé n'est enregistré à la date d'émission.",
        "Le titulaire n'a fait l'objet d'aucune procédure de blocage réglementaire.",
        "La présente attestation reflète la position du compte au jour de son émission.",
    ], columns=2))
    story.append(Spacer(1, 10))
    story.append(_notice(
        styles,
        "La présente attestation est délivrée à la demande de l'intéressé(e) pour servir et valoir ce que de droit, "
        "sous réserve de tout débit ultérieur. Elle ne saurait engager la banque au-delà du solde certifié.",
    ))

    story.append(Spacer(1, 16))

    _render(buf, story, meta)
    buf.seek(0)
    return buf
