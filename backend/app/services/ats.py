"""Deterministic ATS heuristics, ported from the original browser implementation."""
import math
import unicodedata
import regex as re
from app.models import CV, DEFAULT_ORDER

STOPWORDS = set('les des une un le la de du et en au aux pour par sur avec dans est sont vous nous votre vos notre nos ce cette ces qui que quoi dont où ou mais donc car ne pas plus très tout tous toute toutes être avoir fait faire sera seront son sa ses leur leurs il elle ils elles on se sans sous entre chez afin ainsi comme aussi être bien lors après avant poste profil mission missions entreprise équipe équipes candidat candidate recherche recherchons rejoindre the and for with you your our are will from that this have has who what which not but all any can job role team work working experience years year company we they their them about into such other more most must should would'.split(" "))

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[\u0300-\u036f]", "", unicodedata.normalize("NFD", s.lower()))).strip()

def techy(w):
    return bool(re.search(r"[A-Z]{2,}|[0-9+#./]|^[A-Z][a-z]+[A-Z]", w))

def extract_keywords(text: str, maximum: int = 18) -> list[str]:
    matches = list(re.finditer(r"[\p{L}\p{N}][\p{L}\p{N}+#./-]*[\p{L}\p{N}+#]|[\p{L}\p{N}]{2,}", text))
    scores = {}
    def useful(w):
        return norm(w) not in STOPWORDS and (len(w.encode("utf-16-le")) // 2 >= 4 or techy(w))
    def bump(label, score):
        key = norm(label)
        old = scores.get(key, (label, 0))
        scores[key] = (old[0], old[1] + score)
    for i, m in enumerate(matches):
        w = m[0]
        if not useful(w):
            continue
        before = text[:m.start()].rstrip()
        proper = bool(re.match(r"^\p{Lu}", w) and before and not re.search(r"[.!?\n•\-–]$", before))
        bump(w, 3 if techy(w) else 2 if proper else 1)
        if i + 1 < len(matches):
            nxt = matches[i+1][0]
            if useful(nxt) and not techy(w) and not techy(nxt):
                bump(f"{w} {nxt}", .8)
    return [label for label, _ in sorted((v for v in scores.values() if v[1] >= 2), key=lambda v: -v[1])[:maximum]]

def analyse(cv: CV) -> dict:
    p, t = cv.profile, cv.settings.target
    parts = [p.basics.headline, p.basics.summary if "summary" in cv.settings.sections else ""]
    for section in DEFAULT_ORDER:
        if section == "summary" or section not in cv.settings.sections:
            continue
        for item in getattr(p, section):
            if item.include:
                for value in item.model_dump().values():
                    parts.append(" ".join(value) if isinstance(value, list) else value if isinstance(value, str) else "")
    text = norm(" \n ".join(parts))
    keywords = t.keywords or extract_keywords(t.offer_text, 15)
    found = [k for k in keywords if norm(k) in text]
    missing = [k for k in keywords if norm(k) not in text]
    percent = math.floor(100 * len(found) / len(keywords) + .5) if keywords else None
    exp = [e for e in p.experience if e.include]
    skills = [s for s in p.skills if s.include]
    checks = []
    def check(label, ok, hint):
        checks.append(dict(label=label, ok=bool(ok), hint=hint))
    check("Nom et titre", p.basics.full_name and p.basics.headline, "Renseignez votre nom et un titre clair.")
    check("Email et téléphone", p.basics.email and p.basics.phone, "Le recruteur doit pouvoir vous joindre.")
    check("Résumé de 3 à 5 phrases", len(p.basics.summary.strip().encode("utf-16-le"))//2 >= 200, "Au moins 200 caractères, avec vos mots-clés.")
    check("Expériences décrites", exp and all(len(e.description.strip().encode("utf-16-le"))//2 >= 40 for e in exp), "Chaque expérience retenue a besoin d'une description.")
    check("Puces et verbes d'action", any(re.search(r"^\s*[-•]", e.description, re.M) for e in exp), "Une puce « - » par réalisation.")
    check("Au moins 8 compétences", len(skills) >= 8, f"{len(skills)} retenue(s) pour l'instant.")
    check("Formation", any(e.include for e in p.education), "Ajoutez au moins une formation.")
    check("Poste visé renseigné", t.title or t.offer_text.strip(), "Indiquez le poste ou collez l'offre.")
    if percent is not None:
        check("Mots-clés de l'offre couverts (60 %)", percent >= 60, f"{percent} % couverts.")
    return dict(keywords=keywords, found=found, missing=missing, percent=percent,
                score=math.floor(100 * sum(c["ok"] for c in checks) / len(checks) + .5), checks=checks,
                suggested_keywords=extract_keywords(t.offer_text))
