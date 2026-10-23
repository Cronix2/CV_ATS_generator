"""ATS-friendly PDF: real selectable text, Helvetica, single column."""

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer

from app.export.content import Layout

DARK = colors.HexColor("#111111")
GREY = colors.HexColor("#444444")

S = {
    "name": ParagraphStyle("name", fontName="Helvetica-Bold", fontSize=20, leading=24, alignment=TA_CENTER, textColor=DARK),
    "headline": ParagraphStyle("headline", fontName="Helvetica", fontSize=11, leading=14, alignment=TA_CENTER, textColor=GREY),
    "contact": ParagraphStyle("contact", fontName="Helvetica", fontSize=9, leading=12, alignment=TA_CENTER, textColor=GREY),
    "section": ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=11.5, leading=14, textColor=DARK, spaceBefore=10),
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=DARK, spaceBefore=5),
    "meta": ParagraphStyle("meta", fontName="Helvetica-Oblique", fontSize=9.5, leading=12, textColor=GREY),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=10, leading=13, textColor=DARK),
    "bullet": ParagraphStyle("bullet", fontName="Helvetica", fontSize=10, leading=13, textColor=DARK, leftIndent=12, bulletIndent=2),
}


def _p(text: str, style: str | ParagraphStyle, **kw) -> Paragraph:
    # Standard PDF fonts use WinAnsi (cp1252): covers French/most Western text; drop the rest.
    safe = text.encode("cp1252", "ignore").decode("cp1252")
    return Paragraph(escape(safe), S[style] if isinstance(style, str) else style, **kw)


def render_pdf(layout: Layout) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, invariant=1, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=15 * mm, bottomMargin=15 * mm,
        title=f"CV - {layout.name}", author=layout.name, subject=layout.headline,
    )
    # Colour only on the name and section titles: text stays plain, so ATS parsing is unaffected.
    accent = colors.HexColor(layout.accent)
    name_style = ParagraphStyle("name-accent", parent=S["name"], textColor=accent)
    section_style = ParagraphStyle("section-accent", parent=S["section"], textColor=accent)

    story = [_p(layout.name, name_style)]
    if layout.headline:
        story.append(_p(layout.headline, "headline"))
    if layout.contact:
        story.append(_p(" | ".join(layout.contact), "contact"))

    for section in layout.sections:
        story += [_p(section.title.upper(), section_style),
                  HRFlowable(width="100%", thickness=0.7, color=accent, spaceBefore=1, spaceAfter=4)]
        if section.text:
            story.append(_p(section.text, "body"))
        for block in section.blocks:
            head = [_p(block.title, "title")]
            if block.meta:
                head.append(_p(block.meta, "meta"))
            body = [_p(t, "body") for t in block.paragraphs] + [_p(t, "bullet", bulletText="•") for t in block.bullets]
            body += [_p(t, "meta") for t in block.footer]
            # Keep a block's title with its first lines so it never ends a page alone.
            story.append(KeepTogether(head + body[:2]))
            story += body[2:]
        story.append(Spacer(1, 2))

    doc.build(story)
    return buf.getvalue()
