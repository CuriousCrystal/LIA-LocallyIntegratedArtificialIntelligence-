"""
Generates the two project PDFs into this folder.

    python docs\\make_pdfs.py

Kept as a script rather than hand-made PDFs so they can be regenerated when the
project moves on.
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)

HERE = Path(__file__).parent

INK = colors.HexColor("#1d1b20")
MUTED = colors.HexColor("#6b6672")
ACCENT = colors.HexColor("#b4653a")
RULE = colors.HexColor("#ddd8e0")
CODE_BG = colors.HexColor("#f5f2f7")


# ------------------------------------------------------------------ styles ---

def styles():
    s = getSampleStyleSheet()
    base = dict(fontName="Helvetica", textColor=INK, alignment=TA_LEFT)

    s.add(ParagraphStyle("LiaTitle", parent=s["Normal"], fontName="Helvetica-Bold",
                         fontSize=26, leading=30, textColor=INK, spaceAfter=4))
    s.add(ParagraphStyle("LiaSubtitle", parent=s["Normal"], fontName="Helvetica",
                         fontSize=12, leading=16, textColor=MUTED, spaceAfter=18))
    s.add(ParagraphStyle("LiaH1", parent=s["Normal"], fontName="Helvetica-Bold",
                         fontSize=16, leading=20, textColor=INK,
                         spaceBefore=18, spaceAfter=8))
    s.add(ParagraphStyle("LiaH2", parent=s["Normal"], fontName="Helvetica-Bold",
                         fontSize=11.5, leading=15, textColor=ACCENT,
                         spaceBefore=12, spaceAfter=5))
    s.add(ParagraphStyle("LiaBody", parent=s["Normal"], fontSize=10, leading=15,
                         spaceAfter=7, **base))
    s.add(ParagraphStyle("LiaBullet", parent=s["Normal"], fontSize=10, leading=15,
                         spaceAfter=3, **base))
    s.add(ParagraphStyle("LiaNote", parent=s["Normal"], fontName="Helvetica-Oblique",
                         fontSize=9.5, leading=14, textColor=MUTED, spaceAfter=8))
    s.add(ParagraphStyle("LiaCode", parent=s["Normal"], fontName="Courier",
                         fontSize=8.5, leading=12, textColor=INK))
    s.add(ParagraphStyle("LiaCell", parent=s["Normal"], fontSize=9, leading=12,
                         textColor=INK))
    s.add(ParagraphStyle("LiaCellHead", parent=s["Normal"], fontName="Helvetica-Bold",
                         fontSize=9, leading=12, textColor=INK))
    return s


S = styles()


def P(text, style="LiaBody"):
    return Paragraph(text, S[style])


def H1(text):
    return Paragraph(text, S["LiaH1"])


def H2(text):
    return Paragraph(text, S["LiaH2"])


def bullets(items):
    return ListFlowable(
        [ListItem(Paragraph(i, S["LiaBullet"]), leftIndent=12) for i in items],
        bulletType="bullet", bulletColor=ACCENT, bulletFontSize=7,
        leftIndent=14, spaceAfter=8,
    )


def code(text):
    body = Preformatted(text.strip("\n"), S["LiaCode"])
    t = Table([[body]], colWidths=[165 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CODE_BG),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LINEBEFORE", (0, 0), (0, -1), 2, ACCENT),
    ]))
    return KeepTogether([t, Spacer(1, 8)])


def table(rows, widths):
    data = [[Paragraph(c, S["LiaCellHead"]) for c in rows[0]]]
    data += [[Paragraph(c, S["LiaCell"]) for c in r] for r in rows[1:]]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 1, ACCENT),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return KeepTogether([t, Spacer(1, 10)])


def callout(text):
    t = Table([[Paragraph(text, S["LiaCell"])]], colWidths=[165 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fdf6f1")),
        ("LINEBEFORE", (0, 0), (0, -1), 2, ACCENT),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return KeepTogether([t, Spacer(1, 10)])


# -------------------------------------------------------------- rendering ---

def build(path: Path, title: str, subtitle: str, story):
    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(22 * mm, 12 * mm, title)
        canvas.drawRightString(188 * mm, 12 * mm, str(canvas.getPageNumber()))
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.4)
        canvas.line(22 * mm, 16 * mm, 188 * mm, 16 * mm)
        canvas.restoreState()

    doc = BaseDocTemplate(
        str(path), pagesize=A4,
        leftMargin=22 * mm, rightMargin=22 * mm,
        topMargin=20 * mm, bottomMargin=22 * mm,
        title=title, author="Lia",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin,
                  doc.width, doc.height, id="body")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=decorate)])

    head = [Paragraph(title, S["LiaTitle"]), Paragraph(subtitle, S["LiaSubtitle"])]
    doc.build(head + story)
    print(f"wrote {path.name}")
