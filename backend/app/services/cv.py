"""CV rendering and safe download names. No HTTP or persistence dependency."""
import re
import unicodedata
from dataclasses import dataclass

from app.export.content import build
from app.export.docx_export import render_docx
from app.export.pdf_export import render_pdf
from app.models import CV
from app.security import PublicError


def download_name(full_name: str, fmt: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", full_name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_name.replace("'", "")).strip("-")[:60] or "cv"
    return f"CV-{slug}.{fmt}"


@dataclass(frozen=True)
class Rendered:
    data: bytes
    mime: str
    filename: str


def render(cv: CV, fmt: str) -> Rendered:
    layout = build(cv)
    if fmt == "pdf":
        data, mime = render_pdf(layout), "application/pdf"
    elif fmt == "docx":
        data, mime = render_docx(layout), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        raise PublicError("Format inconnu (pdf ou docx).")
    return Rendered(data, mime, download_name(layout.name, fmt))
