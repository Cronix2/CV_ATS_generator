"""Turn the raw text lines of LinkedIn list items into structured profile entries.

LinkedIn's CSS classes are obfuscated and change often, so the scraper only
extracts the *visible text lines* of every list item (plus nested items and
links). The heuristics below map those lines to fields. Everything stays
editable in the UI afterwards, and the optional LLM agents can fix leftovers.
"""

import re
from dataclasses import dataclass, field

from app.models import (
    Certification, Course, Education, Experience, Honor, Language, Project,
    Publication, Skill, Volunteering,
)


@dataclass
class Entry:
    lines: list[str]
    links: list[str] = field(default_factory=list)
    children: list["Entry"] = field(default_factory=list)


# --------------------------------------------------------------------------- dates

MONTHS = {
    "jan": 1, "janv": 1, "janvier": 1, "january": 1,
    "feb": 2, "fév": 2, "févr": 2, "fev": 2, "février": 2, "february": 2,
    "mar": 3, "mars": 3, "march": 3,
    "apr": 4, "avr": 4, "avril": 4, "april": 4,
    "may": 5, "mai": 5,
    "jun": 6, "juin": 6, "june": 6,
    "jul": 7, "juil": 7, "juillet": 7, "july": 7,
    "aug": 8, "août": 8, "aout": 8, "august": 8,
    "sep": 9, "sept": 9, "septembre": 9, "september": 9,
    "oct": 10, "octobre": 10, "october": 10,
    "nov": 11, "novembre": 11, "november": 11,
    "dec": 12, "déc": 12, "décembre": 12, "december": 12,
}
PRESENT = re.compile(r"^(present|aujourd[’']hui|actuel|current|now|en cours)$", re.I)
YEAR = re.compile(r"\b(19|20)\d{2}\b")
RANGE_SPLIT = re.compile(r"\s+[-–—]\s+|\s*[–—]\s*")
DURATION = re.compile(r"\b\d+\s*(yrs?|mos?|ans?|mois|years?|months?)\b", re.I)
NOISE = re.compile(
    r"^(…|\.\.\.)?\s*(see more|voir plus|show all|afficher (tout|plus)|show credential|"
    r"afficher l[’']identifiant|see credential|show project|endorse|recommander)\b", re.I,
)
# Lines that are neither description nor data ("Associated with …", "Contributors: …").
ASSOCIATED = re.compile(r"^(associated with|associé(\(e\)|e)? à|contributors|contributeurs)\b", re.I)
SKILLS_LINE = re.compile(r"^(skills|compétences)\s*:\s*", re.I)
# "A, B and +3 skills" / "A, B et 14 compétences de plus"
SKILLS_SUMMARY = re.compile(r"\s+(and|et)\s+\+?\d+\s+(more\s+)?(skills?|compétences?)(\s+de plus)?$", re.I)
SKILLS_COUNT = re.compile(r"^\+?\d+\s+(more\s+)?(skills?|compétences?)", re.I)  # "+3 compétences"
EMPLOYMENT_TYPES = re.compile(
    r"^(full[- ]time|part[- ]time|self[- ]employed|freelance|contract|internship|apprenticeship|"
    r"seasonal|temps plein|temps partiel|indépendant|cdi|cdd|stage|alternance|apprentissage|"
    r"intérim|saisonnier|contrat en alternance|contrat d[’']apprentissage|contrat de professionnalisation)$", re.I,
)


def normalize_date(text: str) -> tuple[str, bool]:
    """'Jan 2020' -> ('01/2020', False); 'Present' -> ('', True); '2019' -> ('2019', False)."""
    text = text.strip().strip(".")
    if PRESENT.match(text):
        return "", True
    year = YEAR.search(text)
    if not year:
        return text, False
    word = re.match(r"([^\W\d_]+)\.?", text)
    month = MONTHS.get(word.group(1).lower()) if word else None
    return (f"{month:02d}/{year.group(0)}" if month else year.group(0)), False


def is_date_line(line: str) -> bool:
    if len(line) > 80 or not (YEAR.search(line) or PRESENT.search(line.split("·")[0].strip())):
        return False
    head = line.split("·")[0]
    return bool(RANGE_SPLIT.search(head) or DURATION.search(line) or re.fullmatch(r"[^\W\d_]*\.?\s*\d{4}", head.strip()))


def parse_range(line: str) -> tuple[str, str, bool]:
    """'Jan 2020 - Present · 4 yrs' -> ('01/2020', '', True)."""
    head = line.split("·")[0].strip()
    parts = RANGE_SPLIT.split(head, maxsplit=1)
    start, _ = normalize_date(parts[0])
    if len(parts) == 1:
        return start, "", False
    end, current = normalize_date(parts[1])
    return start, end, current


def _strip_prefix(line: str, *prefixes: str) -> str:
    for p in prefixes:
        if line.lower().startswith(p.lower()):
            return line[len(p):].strip(" :")
    return line


# --------------------------------------------------------------------------- helpers

def _clean(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        line = line.replace("\xa0", " ").replace(" ", " ")  # LinkedIn's French typography
        # Collapse spaces but keep line breaks (descriptions are multi-line).
        line = "\n".join(s for s in (re.sub(r"[^\S\n]+", " ", x).strip() for x in line.splitlines()) if s)
        if not line or NOISE.match(line) or (out and out[-1] == line):
            continue
        out.append(line)
    return out


def _split_rest(lines: list[str]) -> tuple[str, list[str]]:
    """Split trailing lines into (description, skills)."""
    desc, skills = [], []
    for line in lines:
        if SKILLS_LINE.match(line):
            skills += [s.strip() for s in re.split(r"[·,]", SKILLS_LINE.sub("", line))
                       if s.strip() and not SKILLS_COUNT.match(s.strip())]
        elif SKILLS_SUMMARY.search(line):
            skills += [s.strip() for s in SKILLS_SUMMARY.sub("", line).split(",") if s.strip()]
        elif not ASSOCIATED.match(line):
            desc.append(line)
    return "\n".join(desc), skills


LOCATION_HINT = re.compile(
    r"(,|·|\b(remote|hybrid|on-site|télétravail|hybride|sur site|region|area|région|metropolitan|métropole)\b)", re.I)


def _looks_like_location(line: str) -> bool:
    if len(line) > 100 or "\n" in line or line.endswith((".", ":")) or line.startswith(("-", "•", "*")):
        return False
    return bool(LOCATION_HINT.search(line)) or len(line.split()) <= 2


def _external(links: list[str]) -> str:
    """First external link that is a page (credential, project…), not a badge/thumbnail image."""
    return next((l for l in links if l.startswith("http") and "linkedin.com" not in l
                 and not re.search(r"\.(png|jpe?g|gif|svg|webp)(\?|$)", l, re.I)), "")


# --------------------------------------------------------------------------- sections

def _role(lines: list[str], company: str = "", employment_type: str = "", location: str = "") -> Experience:
    exp = Experience(title=lines[0] if lines else "", company=company,
                     employment_type=employment_type, location=location)
    i = 1
    if i < len(lines) and not is_date_line(lines[i]):
        parts = [p.strip() for p in lines[i].split("·")]
        if company and EMPLOYMENT_TYPES.match(parts[0]):
            exp.employment_type = parts[0]
            i += 1
        elif not company:
            exp.company = parts[0]
            exp.employment_type = parts[1] if len(parts) > 1 else ""
            i += 1
    if i < len(lines) and is_date_line(lines[i]):
        exp.start, exp.end, exp.current = parse_range(lines[i])
        i += 1
    if i < len(lines) and _looks_like_location(lines[i]) and not SKILLS_LINE.match(lines[i]):
        exp.location = lines[i].split("·")[0].strip()
        i += 1
    exp.description, exp.skills = _split_rest(lines[i:])
    return exp


def parse_experience(entries: list[Entry]) -> list[Experience]:
    out: list[Experience] = []
    for e in entries:
        lines = _clean(e.lines)
        roles = [c for c in e.children if any(is_date_line(l) for l in _clean(c.lines))]
        if roles and lines:
            # Several positions grouped under one company: header = company, "Full-time · 5 yrs", location
            first = lines[1].split("·")[0].strip() if len(lines) > 1 else ""
            emp = first if EMPLOYMENT_TYPES.match(first) else ""
            loc = next((l for l in lines[1:] if not DURATION.search(l) and _looks_like_location(l)), "")
            loc = loc.split("·")[0].strip()
            for c in roles:
                out.append(_role(_clean(c.lines), company=lines[0], employment_type=emp, location=loc))
        elif lines:
            out.append(_role(lines))
    return out


def parse_education(entries: list[Entry]) -> list[Education]:
    out = []
    for e in entries:
        lines = _clean(e.lines)
        if not lines:
            continue
        ed = Education(school=lines[0])
        rest = []
        for line in lines[1:]:
            if not ed.start and is_date_line(line):
                ed.start, ed.end, _ = parse_range(line)
            elif re.match(r"^(grade|note|mention|niveau)\s*:", line, re.I):
                ed.grade = line.split(":", 1)[1].strip()
            elif not ed.degree and not ed.start and not rest:
                degree, _, fld = line.partition(", ")
                ed.degree, ed.field = degree.strip(), fld.strip()
            else:
                rest.append(_strip_prefix(line, "Activities and societies:", "Activités et associations :"))
        ed.description, _ = _split_rest(rest)
        out.append(ed)
    return out


def parse_certifications(entries: list[Entry]) -> list[Certification]:
    out = []
    for e in entries:
        lines = _clean(e.lines)
        if not lines:
            continue
        c = Certification(name=lines[0], url=_external(e.links))
        for line in lines[1:]:
            low = line.lower()
            if low.startswith(("issued", "délivr", "emis", "émis")):
                parts = [p.strip() for p in line.split("·")]
                c.issued = normalize_date(re.sub(r"^\S+( en| le)?\s+", "", parts[0]))[0]
                if len(parts) > 1:
                    c.expires = normalize_date(re.sub(r"^\S+( en| le)?\s+", "", parts[1]))[0]
            elif low.startswith(("credential id", "id de", "identifiant")):
                c.credential_id = re.sub(r"^(credential id|id de (la )?certification|identifiant[^:]*:?)\s*", "", line, flags=re.I)
            elif not c.issuer and not SKILLS_LINE.match(line):
                c.issuer = line
        out.append(c)
    return out


def parse_skills(entries: list[Entry]) -> list[Skill]:
    seen, out = set(), []
    for e in entries:
        lines = _clean(e.lines)
        if lines and lines[0].lower() not in seen and len(lines[0]) <= 80:
            seen.add(lines[0].lower())
            out.append(Skill(name=lines[0]))
    return out


def parse_languages(entries: list[Entry]) -> list[Language]:
    return [Language(name=l[0], proficiency=l[1] if len(l) > 1 else "")
            for l in (_clean(e.lines) for e in entries) if l]


def parse_projects(entries: list[Entry]) -> list[Project]:
    out = []
    for e in entries:
        lines = _clean(e.lines)
        if not lines:
            continue
        p = Project(name=lines[0], url=_external(e.links))
        rest = lines[1:]
        if rest and is_date_line(rest[0]):
            p.start, p.end, _ = parse_range(rest.pop(0))
        p.description, p.skills = _split_rest(rest)
        out.append(p)
    return out


def parse_volunteering(entries: list[Entry]) -> list[Volunteering]:
    out = []
    for e in entries:
        lines = _clean(e.lines)
        if not lines:
            continue
        v = Volunteering(role=lines[0])
        i = 1
        if i < len(lines) and not is_date_line(lines[i]):
            v.organization = lines[i]
            i += 1
        if i < len(lines) and is_date_line(lines[i]):
            v.start, v.end, v.current = parse_range(lines[i])
            i += 1
        if i < len(lines) and len(lines[i]) <= 40 and "\n" not in lines[i] and not lines[i].endswith("."):
            v.cause = lines[i]  # short category right after the dates ("Arts et culture", "Education")
            i += 1
        v.description, _ = _split_rest(lines[i:])
        out.append(v)
    return out


def _issuer_and_date(line: str) -> tuple[str, str]:
    parts = [p.strip() for p in line.split("·")]
    issuer = re.sub(r"^(issued by|délivré par|émis par)\s*", "", parts[0], flags=re.I)
    date = normalize_date(parts[1])[0] if len(parts) > 1 else ""
    if not date and YEAR.search(issuer) and len(parts) == 1:
        issuer, date = "", normalize_date(issuer)[0]
    return issuer, date


def parse_honors(entries: list[Entry]) -> list[Honor]:
    out = []
    for e in entries:
        lines = _clean(e.lines)
        if not lines:
            continue
        h = Honor(title=lines[0])
        rest = lines[1:]
        if rest and not ASSOCIATED.match(rest[0]):
            h.issuer, h.date = _issuer_and_date(rest.pop(0))
        h.description, _ = _split_rest(rest)
        out.append(h)
    return out


def parse_publications(entries: list[Entry]) -> list[Publication]:
    out = []
    for e in entries:
        lines = _clean(e.lines)
        if not lines:
            continue
        p = Publication(title=lines[0], url=_external(e.links))
        rest = lines[1:]
        if rest and "·" in rest[0] or (rest and YEAR.search(rest[0]) and len(rest[0]) < 80):
            p.publisher, p.date = _issuer_and_date(rest.pop(0))
        p.description, _ = _split_rest(rest)
        out.append(p)
    return out


def parse_courses(entries: list[Entry]) -> list[Course]:
    out = []
    for e in entries:
        lines = [l for l in _clean(e.lines) if not ASSOCIATED.match(l)]
        if lines:
            number = next((l for l in lines[1:] if len(l) <= 20), "")
            out.append(Course(name=lines[0], number=number))
    return out
