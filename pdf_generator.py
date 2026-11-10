"""
pdf_generator.py - Official PDF Document Generator for AkumaBank
Generates official Moroccan banking certificates, card subscription agreements,
RIB attestations, account closure certificates, and transaction statements.
Built using ReportLab.
"""

from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
    HRFlowable,
)
from reportlab.graphics.shapes import Drawing, Rect, String, Circle, Line, Group

from morocco_banking import format_moroccan_rib, format_iban, rib_to_iban, format_card_number
from card_tiers import get_card_tier


# ─────────────────────────────────────────────────────────────────────────────
# PALETTES & STYLING
# ─────────────────────────────────────────────────────────────────────────────

PRIMARY_NAVY = colors.HexColor("#0f2b5c")
SECONDARY_BLUE = colors.HexColor("#1e40af")
ACCENT_BLUE = colors.HexColor("#2563eb")
DARK_TEXT = colors.HexColor("#0f172a")
MUTED_TEXT = colors.HexColor("#475569")
LIGHT_BG = colors.HexColor("#f8fafc")
BORDER_COLOR = colors.HexColor("#cbd5e1")
GOLD_COLOR = colors.HexColor("#d97706")
DANGER_COLOR = colors.HexColor("#b91c1c")
SUCCESS_COLOR = colors.HexColor("#15803d")

# Tier Visual Color Mapping for realistic visual card rendering on PDF
TIER_PDF_STYLES = {
    "standard":  {"bg": "#0f2b5c", "accent": "#38bdf8", "chip": "#d97706", "text": "#ffffff", "name": "VISA CLASSIC"},
    "student":   {"bg": "#0369a1", "accent": "#38bdf8", "chip": "#d97706", "text": "#ffffff", "name": "CAMPUS YOUTH"},
    "women":     {"bg": "#831843", "accent": "#fda4af", "chip": "#f472b6", "text": "#ffffff", "name": "SAYIDATI"},
    "gold":      {"bg": "#78350f", "accent": "#facc15", "chip": "#eab308", "text": "#ffffff", "name": "GOLD PREMIER"},
    "platinum":  {"bg": "#1e293b", "accent": "#cbd5e1", "chip": "#94a3b8", "text": "#ffffff", "name": "PLATINUM ELITE"},
    "infinite":  {"bg": "#09090b", "accent": "#fef08a", "chip": "#d4af37", "text": "#ffffff", "name": "VISA INFINITE"},
    "business":  {"bg": "#0f172a", "accent": "#94a3b8", "chip": "#64748b", "text": "#ffffff", "name": "BUSINESS PRO"},
    "freelance": {"bg": "#27272a", "accent": "#fb923c", "chip": "#d97706", "text": "#ffffff", "name": "SELF-EMPLOYED"},
    "travel":    {"bg": "#0c4a6e", "accent": "#2dd4bf", "chip": "#14b8a6", "text": "#ffffff", "name": "WORLD TRAVEL"},
    "eco":       {"bg": "#064e3b", "accent": "#34d399", "chip": "#10b981", "text": "#ffffff", "name": "GREEN CARD"},
    "family":    {"bg": "#3b0764", "accent": "#c084fc", "chip": "#a855f7", "text": "#ffffff", "name": "FAMILY"},
}


def _get_styles():
    """Build custom ReportLab paragraph styles."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        textColor=PRIMARY_NAVY,
        alignment=1,  # Center
        spaceAfter=4,
    ))

    styles.add(ParagraphStyle(
        "DocSubTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=MUTED_TEXT,
        alignment=1,  # Center
        spaceAfter=12,
    ))

    styles.add(ParagraphStyle(
        "SectionHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=PRIMARY_NAVY,
        spaceBefore=8,
        spaceAfter=4,
    ))

    styles.add(ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=DARK_TEXT,
    ))

    styles.add(ParagraphStyle(
        "TableCellBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=DARK_TEXT,
    ))

    styles.add(ParagraphStyle(
        "TableCellMuted",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=MUTED_TEXT,
    ))

    styles.add(ParagraphStyle(
        "LegalNotice",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7,
        leading=9.5,
        textColor=MUTED_TEXT,
        alignment=0,
    ))

    styles.add(ParagraphStyle(
        "BadgeText",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.white,
        alignment=1,
    ))

    return styles


def _build_header(styles, doc_title: str, sub_title: str, ref_no: str):
    """Create the standardized AkumaBank official header."""
    story = []

    # Top legal institution notice
    header_data = [
        [
            Paragraph("<b>AKUMA BANK S.A.</b><br/><font size=7 color='#475569'>Société Anonyme au Capital de 2 500 000 000 MAD<br/>Agrément Bank Al-Maghrib n° BAM/2026/088 — Casablanca, Maroc</font>", styles["TableCell"]),
            Paragraph(f"<b>RÉFÉRENCE OFFICIELLE :</b><br/><font size=8 color='#0f2b5c'><b>{ref_no}</b></font><br/><font size=7 color='#475569'>Date : {datetime.now().strftime('%d/%m/%Y %H:%M')}</font>", styles["TableCellBold"]),
        ]
    ]
    t_header = Table(header_data, colWidths=[330, 190])
    t_header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t_header)

    story.append(HRFlowable(width="100%", thickness=1.5, color=PRIMARY_NAVY, spaceAfter=8, spaceBefore=4))
    story.append(Paragraph(doc_title, styles["DocTitle"]))
    if sub_title:
        story.append(Paragraph(sub_title, styles["DocSubTitle"]))

    return story


def _draw_visual_card(tier_id: str, card_number: str, holder_name: str, expiry: str = "11/31"):
    """
    Draw a vector credit card corresponding to the tier's template.
    Returns a ReportLab Drawing flowable without any stray background circles.
    """
    cfg = TIER_PDF_STYLES.get(tier_id, TIER_PDF_STYLES["standard"])
    bg_hex = cfg["bg"]
    accent_hex = cfg["accent"]
    chip_hex = cfg["chip"]
    badge_label = cfg["name"]

    w = 280
    h = 160
    d = Drawing(w, h)

    # 1. Card background (clean rounded rect)
    d.add(Rect(0, 0, w, h, rx=10, ry=10, fillColor=colors.HexColor(bg_hex), strokeColor=colors.HexColor(accent_hex), strokeWidth=1.5))

    # 2. Subtle internal frame line (inset border for premium look)
    d.add(Rect(6, 6, w - 12, h - 12, rx=7, ry=7, fillColor=None, strokeColor=colors.HexColor(accent_hex), strokeWidth=0.5))

    # 3. Bank brand logo top-left
    d.add(String(20, h - 24, "AKUMA BANK", fontName="Helvetica-Bold", fontSize=11, fillColor=colors.white))
    d.add(String(20, h - 33, "BANK AL-MAGHRIB COMPLIANT", fontName="Helvetica", fontSize=5.5, fillColor=colors.HexColor(accent_hex)))

    # 4. Tier badge top-right (clean rectangular pill)
    badge_width = len(badge_label) * 5.8 + 14
    d.add(Rect(w - badge_width - 16, h - 26, badge_width, 14, rx=3, ry=3, fillColor=colors.HexColor(accent_hex), strokeColor=None))
    d.add(String(w - badge_width - 10, h - 22, badge_label, fontName="Helvetica-Bold", fontSize=7.5, fillColor=colors.HexColor("#09090b")))

    # 5. EMV Chip graphic (realistic 4-pad metallic chip)
    chip_x, chip_y = 20, 82
    chip_w, chip_h = 38, 28
    d.add(Rect(chip_x, chip_y, chip_w, chip_h, rx=4, ry=4, fillColor=colors.HexColor(chip_hex), strokeColor=colors.HexColor("#fef08a"), strokeWidth=1))
    d.add(Line(chip_x, chip_y + 14, chip_x + chip_w, chip_y + 14, strokeColor=colors.HexColor("#78350f"), strokeWidth=0.8))
    d.add(Line(chip_x + 19, chip_y, chip_x + 19, chip_y + chip_h, strokeColor=colors.HexColor("#78350f"), strokeWidth=0.8))
    d.add(Line(chip_x + 9, chip_y + 5, chip_x + 9, chip_y + chip_h - 5, strokeColor=colors.HexColor("#78350f"), strokeWidth=0.5))
    d.add(Line(chip_x + 29, chip_y + 5, chip_x + 29, chip_y + chip_h - 5, strokeColor=colors.HexColor("#78350f"), strokeWidth=0.5))

    # 6. Contactless wave indicator (crisp typography waves)
    d.add(String(chip_x + 46, chip_y + 9, "))))", fontName="Helvetica-Bold", fontSize=12, fillColor=colors.HexColor(accent_hex)))

    # 7. Masked Card Number (spaced high-contrast monospace)
    masked_num = format_card_number(card_number, masked=True)
    d.add(String(20, 52, masked_num, fontName="Courier-Bold", fontSize=13, fillColor=colors.white))

    # 8. Valid Thru & Expiry Date
    d.add(String(160, 31, "VALID THRU", fontName="Helvetica", fontSize=5.5, fillColor=colors.HexColor("#94a3b8")))
    d.add(String(160, 20, expiry, fontName="Courier-Bold", fontSize=9, fillColor=colors.white))

    # 9. Cardholder Name
    clean_name = (holder_name or "VALUED CLIENT").upper()[:24]
    d.add(String(20, 20, clean_name, fontName="Helvetica-Bold", fontSize=9, fillColor=colors.white))

    # 10. Card Brand Logo on bottom-right (VISA / PRIVILEGE)
    d.add(String(w - 48, 20, "VISA", fontName="Helvetica-BoldOblique", fontSize=12, fillColor=colors.white))

    return d


def _draw_stamp_and_signature():
    """Draw official bank seal and signature block."""
    w = 520
    h = 80
    d = Drawing(w, h)

    # Bank Circular Seal Graphic on left
    cx, cy = 100, 40
    d.add(Circle(cx, cy, 32, fillColor=None, strokeColor=PRIMARY_NAVY, strokeWidth=1.5))
    d.add(Circle(cx, cy, 27, fillColor=None, strokeColor=PRIMARY_NAVY, strokeWidth=0.75))
    d.add(String(cx - 24, cy + 12, "AKUMA BANK", fontName="Helvetica-Bold", fontSize=7, fillColor=PRIMARY_NAVY))
    d.add(String(cx - 22, cy, "SIEGE SOCIAL", fontName="Helvetica-Bold", fontSize=6.5, fillColor=PRIMARY_NAVY))
    d.add(String(cx - 24, cy - 12, "CASABLANCA", fontName="Helvetica-Bold", fontSize=6.5, fillColor=PRIMARY_NAVY))

    # Authorized Signature Line on right
    d.add(Line(320, 35, 490, 35, strokeColor=MUTED_TEXT, strokeWidth=1))
    d.add(String(330, 22, "Direction des Opérations Bancaires", fontName="Helvetica", fontSize=7.5, fillColor=MUTED_TEXT))
    d.add(String(345, 10, "Cachet & Signature Électronique", fontName="Helvetica-Bold", fontSize=7.5, fillColor=PRIMARY_NAVY))

    return d


# ─────────────────────────────────────────────────────────────────────────────
# 1. ACCOUNT OPENING CERTIFICATE & WELCOME PACK (WITH CARD TEMPLATE)
# ─────────────────────────────────────────────────────────────────────────────

def generate_opening_certificate_pdf(account: dict, customer: dict, branch: dict, tier: dict) -> BytesIO:
    """Generate official Welcome Pack & Account Opening Certificate."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = _get_styles()
    story = []

    ref_no = f"AKM-OPN-{account.get('AccountID', 0):05d}-{datetime.now().strftime('%Y%m%d')}"
    story.extend(_build_header(
        styles,
        "OFFICIAL ACCOUNT OPENING CERTIFICATE & WELCOME PACK",
        "ATTESTATION OFFICIELLE D'OUVERTURE DE COMPTE ET REMISE DE CARTE",
        ref_no,
    ))

    # 1. Customer & Account Information Table
    story.append(Paragraph("1. Account Holder & Identification", styles["SectionHeader"]))
    iban = rib_to_iban(account.get("AccountNumber", ""))
    cust_data = [
        [
            Paragraph("<b>Full Name:</b>", styles["TableCellBold"]),
            Paragraph(str(customer.get("Name", "N/A")), styles["TableCell"]),
            Paragraph("<b>National ID (CIN):</b>", styles["TableCellBold"]),
            Paragraph(str(customer.get("NationalID", "N/A")), styles["TableCell"]),
        ],
        [
            Paragraph("<b>Email:</b>", styles["TableCellBold"]),
            Paragraph(str(customer.get("Email", "N/A")), styles["TableCell"]),
            Paragraph("<b>Phone:</b>", styles["TableCellBold"]),
            Paragraph(str(customer.get("Phone", "N/A")), styles["TableCell"]),
        ],
        [
            Paragraph("<b>Address:</b>", styles["TableCellBold"]),
            Paragraph(str(customer.get("Address", "N/A")), styles["TableCell"]),
            Paragraph("<b>Branch:</b>", styles["TableCellBold"]),
            Paragraph(f"{branch.get('BranchName', 'Main Branch')} ({branch.get('City', 'Casablanca')})", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Account Number:</b>", styles["TableCellBold"]),
            Paragraph(f"<font color='#0f2b5c'><b>{account.get('AccountNumber', 'N/A')}</b></font>", styles["TableCellBold"]),
            Paragraph("<b>Account Type:</b>", styles["TableCellBold"]),
            Paragraph(str(account.get("AccountType", "Current")), styles["TableCell"]),
        ],
        [
            Paragraph("<b>24-Digit Moroccan RIB:</b>", styles["TableCellBold"]),
            Paragraph(f"<font face='Courier-Bold' color='#0f2b5c'>{format_moroccan_rib(account.get('AccountNumber', ''))}</font>", styles["TableCellBold"]),
            Paragraph("<b>Moroccan IBAN:</b>", styles["TableCellBold"]),
            Paragraph(f"<font face='Courier-Bold' size=7.5>{format_iban(iban)}</font>", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Opening Date:</b>", styles["TableCellBold"]),
            Paragraph(str(account.get("OpeningDate", datetime.now().strftime("%Y-%m-%d"))), styles["TableCell"]),
            Paragraph("<b>Initial Deposit:</b>", styles["TableCellBold"]),
            Paragraph(f"<b>MAD {float(account.get('Balance', 0)):,.2f}</b>", styles["TableCellBold"]),
        ],
    ]
    t_cust = Table(cust_data, colWidths=[120, 140, 110, 150])
    t_cust.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t_cust)

    story.append(Spacer(1, 10))

    # 2. Chosen Card Subscription & Visual Card Template Preview
    story.append(Paragraph("2. Card Subscription & Visual Card Template Issued", styles["SectionHeader"]))

    card_drawing = _draw_visual_card(
        tier_id=tier.get("id", "standard"),
        card_number=account.get("CardNumber", "4240123456789012"),
        holder_name=customer.get("Name", "VALUED CLIENT"),
    )

    perks_html = "".join([f"• {p}<br/>" for p in tier.get("perks", [])])
    tier_details = [
        [
            card_drawing,
            [
                Paragraph(f"<b>Card Subscription:</b> <font color='#0f2b5c'>{tier.get('name', 'Essential Pack')}</font>", styles["TableCellBold"]),
                Spacer(1, 3),
                Paragraph(f"<b>Category:</b> {tier.get('category', 'Personal')} &bull; <b>Tier Badge:</b> {tier.get('badge', 'VISA')}", styles["TableCell"]),
                Spacer(1, 3),
                Paragraph(f"<b>Monthly Fee:</b> <font color='#0f2b5c'><b>{tier.get('monthly_fee', '0 MAD / month')}</b></font>", styles["TableCellBold"]),
                Spacer(1, 3),
                Paragraph(f"<b>Account Ceiling (Max Balance):</b> <font color='#1e40af'><b>{tier.get('plafond', '100,000 MAD')}</b></font>", styles["TableCellBold"]),
                Spacer(1, 3),
                Paragraph("<b>Key Privileges & Perks Included:</b>", styles["TableCellBold"]),
                Spacer(1, 2),
                Paragraph(f"<font size=7.5 color='#334155'>{perks_html}</font>", styles["TableCell"]),
            ]
        ]
    ]
    t_tier = Table(tier_details, colWidths=[290, 230])
    t_tier.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f5f9")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#94a3b8")),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(t_tier)

    story.append(Spacer(1, 10))

    # 3. Regulatory compliance notice & signature block
    story.append(Paragraph("3. Regulatory & Legal Acknowledgement", styles["SectionHeader"]))
    compliance_text = (
        "This account is governed by Moroccan Law n° 103-12 relating to credit institutions and similar bodies, "
        "and circulars issued by Bank Al-Maghrib. The 24-digit RIB conforms strictly to the Modulo 97 standard. "
        "The customer certifies the accuracy of information submitted and acknowledges receiving the terms of the subscription."
    )
    story.append(Paragraph(compliance_text, styles["LegalNotice"]))

    story.append(Spacer(1, 10))
    story.append(_draw_stamp_and_signature())

    doc.build(story)
    buf.seek(0)
    return buf


# ─────────────────────────────────────────────────────────────────────────────
# 2. ACCOUNT CLOSURE CERTIFICATE & DISCHARGE (ATTESTATION DE CLÔTURE ET QUITTUS)
# ─────────────────────────────────────────────────────────────────────────────

def generate_closure_certificate_pdf(account: dict, customer: dict, branch: dict, reason: str = None) -> BytesIO:
    """Generate official Account Closure Certificate & Quittus."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = _get_styles()
    story = []

    ref_no = f"AKM-CLS-{account.get('AccountID', 0):05d}-{datetime.now().strftime('%Y%m%d')}"
    story.extend(_build_header(
        styles,
        "OFFICIAL CERTIFICATE OF ACCOUNT CLOSURE & DISCHARGE",
        "ATTESTATION OFFICIELLE DE CLÔTURE DE COMPTE ET QUITTUS DÉFINITIF",
        ref_no,
    ))

    closure_reason = reason or "Customer Request / Mutual Agreement"

    # Statement of Discharge
    statement = (
        f"<b>Akuma Bank S.A.</b> hereby certifies that the bank account designated below, registered in our records "
        f"under the name of <b>{customer.get('Name', 'N/A')}</b>, has been <b>definitively closed and liquidated</b> "
        f"effective as of <b>{datetime.now().strftime('%d/%m/%Y')}</b>, in accordance with applicable Moroccan banking regulations."
    )
    story.append(Paragraph(statement, styles["TableCell"]))
    story.append(Spacer(1, 10))

    # Account Closure Summary Table
    story.append(Paragraph("Account & Liquidation Details", styles["SectionHeader"]))
    table_data = [
        [Paragraph("<b>Account Holder:</b>", styles["TableCellBold"]), Paragraph(str(customer.get("Name", "N/A")), styles["TableCell"])],
        [Paragraph("<b>National ID (CIN):</b>", styles["TableCellBold"]), Paragraph(str(customer.get("NationalID", "N/A")), styles["TableCell"])],
        [Paragraph("<b>Account Number:</b>", styles["TableCellBold"]), Paragraph(str(account.get("AccountNumber", "N/A")), styles["TableCell"])],
        [Paragraph("<b>Moroccan RIB:</b>", styles["TableCellBold"]), Paragraph(f"<font face='Courier-Bold'>{format_moroccan_rib(account.get('AccountNumber', ''))}</font>", styles["TableCellBold"])],
        [Paragraph("<b>Managing Branch:</b>", styles["TableCellBold"]), Paragraph(f"{branch.get('BranchName', 'Main Branch')} - {branch.get('City', 'Casablanca')}", styles["TableCell"])],
        [Paragraph("<b>Closure Date:</b>", styles["TableCellBold"]), Paragraph(datetime.now().strftime("%d/%m/%Y %H:%M"), styles["TableCell"])],
        [Paragraph("<b>Closure Reason:</b>", styles["TableCellBold"]), Paragraph(closure_reason, styles["TableCell"])],
        [Paragraph("<b>Final Account Balance:</b>", styles["TableCellBold"]), Paragraph("<font color='#15803d'><b>MAD 0.00 (Cleared in Full)</b></font>", styles["TableCellBold"])],
        [Paragraph("<b>Associated Card Instruments:</b>", styles["TableCellBold"]), Paragraph("<font color='#b91c1c'><b>Deactivated & Permanently Cancelled</b></font>", styles["TableCellBold"])],
        [Paragraph("<b>Account Status:</b>", styles["TableCellBold"]), Paragraph("<font color='#b91c1c'><b>CLOSED (CLÔTURÉ)</b></font>", styles["TableCellBold"])],
    ]
    t = Table(table_data, colWidths=[180, 340])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)

    story.append(Spacer(1, 12))

    # Quittus / Legal Discharge Text
    story.append(Paragraph("Quittus & Release of Reciprocal Commitments", styles["SectionHeader"]))
    quittus_text = (
        "Akuma Bank S.A. confirms that as of this date, all payment means (cards, checks) linked to this account "
        "have been rendered null and void. The account holder is formally discharged from any further maintenance fees "
        "or charges. Likewise, the bank acknowledges that all pending transactions have been fully processed and settled. "
        "This certificate is issued to serve and assert legal rights wherever required."
    )
    story.append(Paragraph(quittus_text, styles["LegalNotice"]))

    story.append(Spacer(1, 25))
    story.append(_draw_stamp_and_signature())

    doc.build(story)
    buf.seek(0)
    return buf


# ─────────────────────────────────────────────────────────────────────────────
# 3. CARD SUBSCRIPTION CERTIFICATE & SPECIFICATION SHEET
# ─────────────────────────────────────────────────────────────────────────────

def generate_card_subscription_pdf(account: dict, customer: dict, tier: dict) -> BytesIO:
    """Generate detailed Card Subscription & Specification Document."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = _get_styles()
    story = []

    ref_no = f"AKM-CRD-{account.get('AccountID', 0):05d}-{datetime.now().strftime('%Y%m%d')}"
    story.extend(_build_header(
        styles,
        "CARD SUBSCRIPTION ATTESTATION & SPECIFICATIONS",
        "ATTESTATION DE CARTE BANCAIRE ET CONDITIONS DE SOUSCRIPTION",
        ref_no,
    ))

    # Prominent Visual Card Drawing
    story.append(Paragraph("1. Card Visual Template & Identification", styles["SectionHeader"]))
    card_drawing = _draw_visual_card(
        tier_id=tier.get("id", "standard"),
        card_number=account.get("CardNumber", "4240123456789012"),
        holder_name=customer.get("Name", "VALUED CLIENT"),
    )
    story.append(KeepTogether([card_drawing]))

    story.append(Spacer(1, 10))

    # Card Specifications Table
    story.append(Paragraph("2. Technical & Financial Specifications", styles["SectionHeader"]))
    spec_data = [
        [Paragraph("<b>Card Product:</b>", styles["TableCellBold"]), Paragraph(f"<b>{tier.get('name', 'N/A')}</b>", styles["TableCellBold"])],
        [Paragraph("<b>Tier Classification:</b>", styles["TableCellBold"]), Paragraph(f"{tier.get('category', 'Personal')} &bull; Badge: {tier.get('badge', 'VISA')}", styles["TableCell"])],
        [Paragraph("<b>Masked Card Number:</b>", styles["TableCellBold"]), Paragraph(f"<font face='Courier-Bold'>{format_card_number(account.get('CardNumber', ''), masked=True)}</font>", styles["TableCellBold"])],
        [Paragraph("<b>Associated RIB:</b>", styles["TableCellBold"]), Paragraph(f"<font face='Courier-Bold'>{format_moroccan_rib(account.get('AccountNumber', ''))}</font>", styles["TableCell"])],
        [Paragraph("<b>Account Balance Ceiling:</b>", styles["TableCellBold"]), Paragraph(f"<font color='#0f2b5c'><b>{tier.get('plafond', 'N/A')}</b></font>", styles["TableCellBold"])],
        [Paragraph("<b>Monthly Maintenance Fee:</b>", styles["TableCellBold"]), Paragraph(f"<b>{tier.get('monthly_fee', '0 MAD / month')}</b>", styles["TableCellBold"])],
        [Paragraph("<b>Contactless NFC Payments:</b>", styles["TableCellBold"]), Paragraph("Enabled (Up to 600 MAD without PIN, compliant with BAM security rules)", styles["TableCell"])],
        [Paragraph("<b>24/7 Emergency Assistance Hotline:</b>", styles["TableCellBold"]), Paragraph("<b>+212 (0) 5 22 00 00 00</b> (Instant blocking / Mise en opposition)", styles["TableCellBold"])],
    ]
    t_spec = Table(spec_data, colWidths=[180, 340])
    t_spec.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("PADDING", (0, 0), (-1, -1), 4.5),
    ]))
    story.append(t_spec)

    story.append(Spacer(1, 8))

    # Perks Box
    story.append(Paragraph("3. Benefits, Insurance & Privileges", styles["SectionHeader"]))
    perks_list = tier.get("perks") or [
        "Nationwide ATM and electronic POS payment acceptance",
        "Bank Al-Maghrib interbank clearing compliance",
        "24/7 client card assistance and fraud prevention",
    ]
    perk_items = [[Paragraph(f"<b>&bull;</b> {p}", styles["TableCell"])] for p in perks_list]
    t_perks = Table(perk_items, colWidths=[520])
    t_perks.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t_perks)

    story.append(Spacer(1, 10))
    story.append(_draw_stamp_and_signature())

    doc.build(story)
    buf.seek(0)
    return buf


# ─────────────────────────────────────────────────────────────────────────────
# 4. OFFICIAL 24-DIGIT MOROCCAN RIB ATTESTATION
# ─────────────────────────────────────────────────────────────────────────────

def generate_rib_attestation_pdf(account: dict, customer: dict, branch: dict) -> BytesIO:
    """Generate official Relevé d'Identité Bancaire (RIB) certificate."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = _get_styles()
    story = []

    ref_no = f"AKM-RIB-{account.get('AccountID', 0):05d}-{datetime.now().strftime('%Y%m%d')}"
    story.extend(_build_header(
        styles,
        "RELEVÉ D'IDENTITÉ BANCAIRE (RIB)",
        "ATTESTATION BANCAIRE OFFICIELLE D'IDENTITÉ ET DE DOMICILIATION",
        ref_no,
    ))

    # Big Prominent RIB Box
    rib_str = account.get("AccountNumber", "")
    iban_str = rib_to_iban(rib_str)

    bank_code = rib_str[:3] if len(rib_str) >= 3 else "240"
    branch_code = rib_str[3:6] if len(rib_str) >= 6 else "810"
    account_seq = rib_str[6:22] if len(rib_str) >= 22 else "0" * 16
    key_code = rib_str[22:24] if len(rib_str) >= 24 else "00"

    rib_breakdown = [
        [
            Paragraph("<b>Code Banque</b><br/><font size=7 color='#64748b'>Bank Code</font>", styles["TableCellMuted"]),
            Paragraph("<b>Code Guichet</b><br/><font size=7 color='#64748b'>Branch Code</font>", styles["TableCellMuted"]),
            Paragraph("<b>Numéro de Compte</b><br/><font size=7 color='#64748b'>Account Number (16 Digits)</font>", styles["TableCellMuted"]),
            Paragraph("<b>Clé RIB</b><br/><font size=7 color='#64748b'>Key (Modulo 97)</font>", styles["TableCellMuted"]),
        ],
        [
            Paragraph(f"<font size=12 face='Courier-Bold' color='#0f2b5c'><b>{bank_code}</b></font>", styles["TableCell"]),
            Paragraph(f"<font size=12 face='Courier-Bold' color='#0f2b5c'><b>{branch_code}</b></font>", styles["TableCell"]),
            Paragraph(f"<font size=12 face='Courier-Bold' color='#0f2b5c'><b>{account_seq}</b></font>", styles["TableCell"]),
            Paragraph(f"<font size=12 face='Courier-Bold' color='#1e40af'><b>{key_code}</b></font>", styles["TableCell"]),
        ]
    ]
    t_rib = Table(rib_breakdown, colWidths=[80, 80, 280, 80])
    t_rib.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f5f9")),
        ("GRID", (0, 0), (-1, -1), 1, colors.HexColor("#94a3b8")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t_rib)

    story.append(Spacer(1, 10))

    # Full formatted RIB & IBAN Callout
    full_callout = [
        [
            Paragraph("<b>FULL 24-DIGIT RIB :</b>", styles["TableCellBold"]),
            Paragraph(f"<font size=11 face='Courier-Bold' color='#0f2b5c'><b>{format_moroccan_rib(rib_str)}</b></font>", styles["TableCellBold"]),
        ],
        [
            Paragraph("<b>INTERNATIONAL IBAN :</b>", styles["TableCellBold"]),
            Paragraph(f"<font size=10 face='Courier-Bold' color='#1e40af'><b>{format_iban(iban_str)}</b></font>", styles["TableCellBold"]),
        ],
        [
            Paragraph("<b>SWIFT / BIC CODE :</b>", styles["TableCellBold"]),
            Paragraph("<font size=10 face='Courier-Bold'><b>AKUMMAMCXXX</b></font>", styles["TableCellBold"]),
        ],
    ]
    t_callout = Table(full_callout, colWidths=[160, 360])
    t_callout.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eff6ff")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#3b82f6")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t_callout)

    story.append(Spacer(1, 12))

    # Account Holder & Branch Domiciliation
    story.append(Paragraph("Titulaire du Compte & Domiciliation Bancaire", styles["SectionHeader"]))
    holder_data = [
        [Paragraph("<b>Titulaire / Account Holder:</b>", styles["TableCellBold"]), Paragraph(str(customer.get("Name", "N/A")), styles["TableCell"])],
        [Paragraph("<b>Identifiant National (CIN):</b>", styles["TableCellBold"]), Paragraph(str(customer.get("NationalID", "N/A")), styles["TableCell"])],
        [Paragraph("<b>Adresse:</b>", styles["TableCellBold"]), Paragraph(str(customer.get("Address", "N/A")), styles["TableCell"])],
        [Paragraph("<b>Banque Domiciliataire:</b>", styles["TableCellBold"]), Paragraph("AKUMA BANK S.A. — Casablanca, Maroc", styles["TableCell"])],
        [Paragraph("<b>Agence / Branch:</b>", styles["TableCellBold"]), Paragraph(f"{branch.get('BranchName', 'Main Branch')} &bull; {branch.get('Address', '')}, {branch.get('City', '')}", styles["TableCell"])],
        [Paragraph("<b>Nature du Compte:</b>", styles["TableCellBold"]), Paragraph(f"Compte {account.get('AccountType', 'Current')} en Dirhams marocains (MAD)", styles["TableCell"])],
    ]
    t_holder = Table(holder_data, colWidths=[180, 340])
    t_holder.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t_holder)

    story.append(Spacer(1, 15))

    # Legal validation notice
    notice = (
        "Le présent Relevé d'Identité Bancaire est délivré pour servir et valoir ce que de droit, notamment "
        "pour la mise en place de virements (salaires, remboursements, prestations) et de prélèvements automatiques. "
        "Document authentifié numériquement sous contrôle de Bank Al-Maghrib."
    )
    story.append(Paragraph(notice, styles["LegalNotice"]))

    story.append(Spacer(1, 20))
    story.append(_draw_stamp_and_signature())

    doc.build(story)
    buf.seek(0)
    return buf


# ─────────────────────────────────────────────────────────────────────────────
# 5. ACCOUNT STATEMENT & ACTIVITY LOG (RELEVÉ BANCAIRE)
# ─────────────────────────────────────────────────────────────────────────────

def generate_statement_pdf(account: dict, customer: dict, branch: dict, transactions: list) -> BytesIO:
    """Generate official Account Statement & Activity Log."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = _get_styles()
    story = []

    ref_no = f"AKM-STM-{account.get('AccountID', 0):05d}-{datetime.now().strftime('%Y%m%d')}"
    story.extend(_build_header(
        styles,
        "ACCOUNT STATEMENT & ACTIVITY LOG",
        "RELEVÉ OFFICIEL DE COMPTE ET HISTORIQUE DES TRANSACTIONS",
        ref_no,
    ))

    # Financial Summary Metrics
    current_balance = float(account.get("Balance", 0.0))
    total_credits = sum(float(t.get("Amount", 0)) for t in transactions if t.get("TransactionType") == "Deposit")
    total_debits = sum(float(t.get("Amount", 0)) for t in transactions if t.get("TransactionType") in ("Withdrawal", "Transfer"))

    summary_data = [
        [
            Paragraph("<b>Account Holder:</b>", styles["TableCellBold"]),
            Paragraph(str(customer.get("Name", "N/A")), styles["TableCell"]),
            Paragraph("<b>Current Balance:</b>", styles["TableCellBold"]),
            Paragraph(f"<font color='#0f2b5c' size=10><b>MAD {current_balance:,.2f}</b></font>", styles["TableCellBold"]),
        ],
        [
            Paragraph("<b>Account Number:</b>", styles["TableCellBold"]),
            Paragraph(str(account.get("AccountNumber", "N/A")), styles["TableCell"]),
            Paragraph("<b>Total Inflows (Credits):</b>", styles["TableCellBold"]),
            Paragraph(f"<font color='#15803d'><b>+MAD {total_credits:,.2f}</b></font>", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Moroccan RIB:</b>", styles["TableCellBold"]),
            Paragraph(f"<font face='Courier' size=7.5>{format_moroccan_rib(account.get('AccountNumber', ''))}</font>", styles["TableCell"]),
            Paragraph("<b>Total Outflows (Debits):</b>", styles["TableCellBold"]),
            Paragraph(f"<font color='#b91c1c'><b>-MAD {total_debits:,.2f}</b></font>", styles["TableCell"]),
        ],
    ]
    t_sum = Table(summary_data, colWidths=[120, 150, 130, 120])
    t_sum.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t_sum)

    story.append(Spacer(1, 10))

    # Transactions Table
    story.append(Paragraph(f"Transaction Activity Log ({len(transactions)} Records)", styles["SectionHeader"]))

    headers = [
        Paragraph("<b>Date / Time</b>", styles["TableCellBold"]),
        Paragraph("<b>Type</b>", styles["TableCellBold"]),
        Paragraph("<b>Description</b>", styles["TableCellBold"]),
        Paragraph("<b>Amount (MAD)</b>", styles["TableCellBold"]),
        Paragraph("<b>Balance (MAD)</b>", styles["TableCellBold"]),
    ]
    rows = [headers]

    for tx in transactions[:45]:  # Fits cleanly on page
        t_type = tx.get("TransactionType", "N/A")
        amt = float(tx.get("Amount", 0))
        bal = float(tx.get("BalanceAfter", 0))
        amt_str = f"+{amt:,.2f}" if t_type == "Deposit" else f"-{amt:,.2f}"
        amt_color = "#15803d" if t_type == "Deposit" else "#b91c1c"

        rows.append([
            Paragraph(str(tx.get("TransactionDate", ""))[:19], styles["TableCellMuted"]),
            Paragraph(t_type, styles["TableCell"]),
            Paragraph(str(tx.get("Description", "N/A"))[:42], styles["TableCell"]),
            Paragraph(f"<font color='{amt_color}'><b>{amt_str}</b></font>", styles["TableCell"]),
            Paragraph(f"<b>{bal:,.2f}</b>", styles["TableCellBold"]),
        ])

    if len(rows) == 1:
        rows.append([Paragraph("No transactions recorded on this account.", styles["TableCell"]), "", "", "", ""])

    t_tx = Table(rows, colWidths=[100, 70, 190, 80, 80])
    t_tx.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("PADDING", (0, 0), (-1, -1), 3.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(t_tx)

    story.append(Spacer(1, 12))
    notice = "Ce relevé bancaire est certifié conforme aux écritures comptables enregistrées dans le système central d'Akuma Bank."
    story.append(Paragraph(notice, styles["LegalNotice"]))

    doc.build(story)
    buf.seek(0)
    return buf


# ─────────────────────────────────────────────────────────────────────────────
# 6. ATTESTATION DE SOLVABILITÉ ET DE CAPACITÉ FINANCIÈRE
# ─────────────────────────────────────────────────────────────────────────────

def generate_solvency_certificate_pdf(account: dict, customer: dict, branch: dict, purpose: str = None) -> BytesIO:
    """Generate official Bank Solvency & Good Standing Certificate."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = _get_styles()
    story = []

    ref_no = f"AKM-SOL-{account.get('AccountID', 0):05d}-{datetime.now().strftime('%Y%m%d')}"
    story.extend(_build_header(
        styles,
        "ATTESTATION DE SOLVABILITÉ ET DE CAPACITÉ FINANCIÈRE",
        "OFFICIAL CERTIFICATE OF BANK SOLVENCY & FINANCIAL GOOD STANDING",
        ref_no,
    ))

    dest_purpose = purpose or "Visa Application / Administrative Formalities"

    statement = (
        f"La direction d'<b>AKUMA BANK S.A.</b> certifie par la présente que Monsieur / Madame "
        f"<b>{customer.get('Name', 'N/A')}</b>, titulaire de la Carte d'Identité Nationale / Passeport "
        f"n° <b>{customer.get('NationalID', 'N/A')}</b>, est titulaire dans nos livres du compte bancaire désigné ci-après :"
    )
    story.append(Paragraph(statement, styles["TableCell"]))
    story.append(Spacer(1, 10))

    solvency_data = [
        [Paragraph("<b>Titulaire du Compte:</b>", styles["TableCellBold"]), Paragraph(str(customer.get("Name", "N/A")), styles["TableCellBold"])],
        [Paragraph("<b>Identifiant National (CIN):</b>", styles["TableCellBold"]), Paragraph(str(customer.get("NationalID", "N/A")), styles["TableCell"])],
        [Paragraph("<b>Numéro de Compte (RIB 24 chiffres):</b>", styles["TableCellBold"]), Paragraph(f"<font face='Courier-Bold'>{format_moroccan_rib(account.get('AccountNumber', ''))}</font>", styles["TableCellBold"])],
        [Paragraph("<b>Nature du Compte:</b>", styles["TableCellBold"]), Paragraph(f"Compte {account.get('AccountType', 'Current')} en Dirhams (MAD)", styles["TableCell"])],
        [Paragraph("<b>Date d'Ouverture du Compte:</b>", styles["TableCellBold"]), Paragraph(str(account.get("OpeningDate", "2026-01-01")), styles["TableCell"])],
        [Paragraph("<b>Agence Gestionnaire:</b>", styles["TableCellBold"]), Paragraph(f"{branch.get('BranchName', 'Agence Principale')} — {branch.get('City', 'Casablanca')}", styles["TableCell"])],
        [Paragraph("<b>Solde Actuel Certifié:</b>", styles["TableCellBold"]), Paragraph(f"<font color='#0f2b5c' size=10><b>MAD {float(account.get('Balance', 0)):,.2f}</b></font>", styles["TableCellBold"])],
        [Paragraph("<b>Objet / Destination:</b>", styles["TableCellBold"]), Paragraph(f"<b>{dest_purpose}</b>", styles["TableCell"])],
        [Paragraph("<b>Situation du Compte:</b>", styles["TableCellBold"]), Paragraph("<font color='#15803d'><b>Actif &bull; Fonctionnement Régulier et Satisfaisant</b></font>", styles["TableCellBold"])],
    ]
    t = Table(solvency_data, colWidths=[180, 340])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t)

    story.append(Spacer(1, 12))

    cert_text = (
        "Nous attestons que le compte mentionné ci-dessus fonctionne à notre entière satisfaction, "
        "sans incident de paiement ni opposition de quelque nature que ce soit. "
        "La présente attestation est délivrée à la demande de l'intéressé(e) pour servir et valoir ce que de droit, "
        "sous réserve de tout débit ultérieur pouvant intervenir dans le cadre des opérations courantes."
    )
    story.append(Paragraph(cert_text, styles["LegalNotice"]))

    story.append(Spacer(1, 20))
    story.append(_draw_stamp_and_signature())

    doc.build(story)
    buf.seek(0)
    return buf

