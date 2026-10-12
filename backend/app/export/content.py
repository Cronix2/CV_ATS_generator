"""Format-agnostic CV layout shared by the PDF and DOCX exporters.

ATS rules applied: single column, standard section titles, contact details in
the body (not in header/footer), no tables/images/icons, plain bullets,
consistent dates, emojis stripped.
"""

import re
import unicodedata
from dataclasses import dataclass, field

from app.models import CV

LABELS = {
    "fr": {
        "summary": "Profil", "experience": "Expérience professionnelle", "education": "Formation",
        "skills": "Compétences", "certifications": "Certifications", "languages": "Langues",
        "projects": "Projets", "volunteering": "Bénévolat", "honors": "Distinctions",
        "publications": "Publications", "courses": "Cours", "present": "Présent",
        "technologies": "Technologies", "credential": "ID", "grade": "Mention",
    },
    "en": {
        "summary": "Summary", "experience": "Professional Experience", "education": "Education",
        "skills": "Skills", "certifications": "Certifications", "languages": "Languages",
        "projects": "Projects", "volunteering": "Volunteer Experience", "honors": "Honors & Awards",
        "publications": "Publications", "courses": "Courses", "present": "Present",
        "technologies": "Technologies", "credential": "ID", "grade": "Grade",
    },
}

BULLET = re.compile(r"^\s*[-•*–▪●◦]\s*")


@dataclass
class Block:
    title: str = ""
    meta: str = ""                                    # "Company · Location · 01/2020 – Present"
    paragraphs: list[str] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)
    footer: list[str] = field(default_factory=list)  # e.g. "Skills: ..." after the bullets


@dataclass
class Section:
    key: str
    title: str
    blocks: list[Block] = field(default_factory=list)
    text: str = ""                                    # inline sections (summary, skills, languages)


@dataclass
class Layout:
    name: str
    headline: str
    contact: list[str]
    sections: list[Section]
    accent: str = "#111111"


def clean(text: str) -> str:
    """Drop emojis / pictographs that ATS parsers choke on."""
    text = "".join(c for c in text if unicodedata.category(c) not in ("So", "Cs", "Co") and ord(c) <= 0xFFFF)
    return re.sub(r"[ \t]+", " ", text).strip()


def _join(*parts: str, sep: str = " · ") -> str:
    return sep.join(p for p in (clean(x) for x in parts) if p)


def _dates(start: str, end: str, current: bool, present: str) -> str:
    end = present if current else end
    return f"{start} – {end}" if start and end else start or end


def _body(block: Block, text: str) -> Block:
    for line in (l for l in text.splitlines() if l.strip()):
        if BULLET.match(line):
            block.bullets.append(clean(BULLET.sub("", line)))
        elif block.bullets:  # continuation after bullets -> new bullet keeps reading order
            block.bullets.append(clean(line))
        else:
            block.paragraphs.append(clean(line))
    return block


def build(cv: CV) -> Layout:
    p, lang = cv.profile, cv.settings.language
    L = LABELS[lang]
    b = p.basics
    contact = [clean(x) for x in [b.location, b.email, b.phone, b.linkedin_url, *b.websites] if x and x.strip()]
    sections: list[Section] = []

    for key in cv.settings.sections:
        s = Section(key=key, title=L[key])
        if key == "summary":
            s.text = clean(b.summary).replace("\n", " ") if b.summary.strip() else ""
        elif key == "skills":
            s.text = ", ".join(clean(x.name) for x in p.skills if x.include and x.name.strip())
        elif key == "languages":
            s.text = ", ".join(_join(x.name, f"({x.proficiency})" if x.proficiency else "", sep=" ")
                               for x in p.languages if x.include and x.name.strip())
        elif key == "courses":
            s.text = ", ".join(_join(x.name, x.number, sep=" ") for x in p.courses if x.include and x.name.strip())
        elif key == "experience":
            for x in (x for x in p.experience if x.include):
                blk = Block(title=clean(x.title),
                            meta=_join(x.company, x.employment_type, x.location, _dates(x.start, x.end, x.current, L["present"])))
                _body(blk, x.description)
                if x.skills:
                    blk.footer.append(f"{L['skills']} : " + ", ".join(clean(k) for k in x.skills))
                s.blocks.append(blk)
        elif key == "education":
            for x in (x for x in p.education if x.include):
                blk = Block(title=_join(x.degree, x.field, sep=", ") or clean(x.school),
                            meta=_join(x.school if (x.degree or x.field) else "", _dates(x.start, x.end, False, "")))
                if x.grade:
                    blk.paragraphs.append(f"{L['grade']} : {clean(x.grade)}")
                s.blocks.append(_body(blk, x.description))
        elif key == "certifications":
            for x in (x for x in p.certifications if x.include):
                s.blocks.append(Block(title=clean(x.name), meta=_join(
                    x.issuer, x.issued, f"{L['credential']} {x.credential_id}" if x.credential_id else "", x.url)))
        elif key == "projects":
            for x in (x for x in p.projects if x.include):
                blk = _body(Block(title=clean(x.name), meta=_join(_dates(x.start, x.end, False, ""), x.url)), x.description)
                if x.skills:
                    blk.footer.append(f"{L['technologies']} : " + ", ".join(clean(k) for k in x.skills))
                s.blocks.append(blk)
        elif key == "volunteering":
            for x in (x for x in p.volunteering if x.include):
                s.blocks.append(_body(Block(title=clean(x.role), meta=_join(
                    x.organization, x.cause, _dates(x.start, x.end, x.current, L["present"]))), x.description))
        elif key == "honors":
            for x in (x for x in p.honors if x.include):
                s.blocks.append(_body(Block(title=clean(x.title), meta=_join(x.issuer, x.date)), x.description))
        elif key == "publications":
            for x in (x for x in p.publications if x.include):
                s.blocks.append(_body(Block(title=clean(x.title), meta=_join(x.publisher, x.date, x.url)), x.description))
        if s.text or s.blocks:
            sections.append(s)

    return Layout(name=clean(b.full_name), headline=clean(b.headline), contact=contact, sections=sections,
                  accent=cv.settings.accent)
