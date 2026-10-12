// Local, instant ATS heuristics: keyword extraction from the job offer, keyword match, CV quality checks.
import { LIST_KEYS, type CV } from "./types";

const STOPWORDS = new Set(
  (
    "les des une un le la de du et en au aux pour par sur avec dans est sont vous nous votre vos notre nos ce cette ces " +
    "qui que quoi dont où ou mais donc car ne pas plus très tout tous toute toutes être avoir fait faire sera seront " +
    "son sa ses leur leurs il elle ils elles on se sans sous entre chez afin ainsi comme aussi être bien lors après avant " +
    "poste profil mission missions entreprise équipe équipes candidat candidate recherche recherchons rejoindre " +
    "the and for with you your our are will from that this have has who what which not but all any can job role team " +
    "work working experience years year company we they their them about into such other more most must should would"
  ).split(" "),
);

const norm = (s: string) =>
  s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/\s+/g, " ").trim();

const isTechy = (w: string) => /[A-Z]{2,}|[0-9+#./]|^[A-Z][a-z]+[A-Z]/.test(w);

/** Best-effort keyword suggestions from an offer text (editable by the user afterwards). */
export function extractKeywords(text: string, max = 18): string[] {
  const matches = [...text.matchAll(/[\p{L}\p{N}][\p{L}\p{N}+#./-]*[\p{L}\p{N}+#]|[\p{L}\p{N}]{2,}/gu)];
  const tokens = matches.map((m) => m[0]);
  // A capitalised word in the middle of a sentence is usually a tool, language or product ("Python", "Docker").
  const properNoun = (i: number) => {
    const m = matches[i];
    const before = text.slice(0, m.index).trimEnd();
    // ":" does not start a sentence: "Compétences : Python, SQL" is a list of keywords.
    return /^\p{Lu}/u.test(m[0]) && before !== "" && !/[.!?\n•\-–]$/.test(before);
  };
  const scores = new Map<string, { label: string; score: number }>();
  const bump = (label: string, score: number) => {
    const key = norm(label);
    const cur = scores.get(key);
    scores.set(key, { label: cur?.label ?? label, score: (cur?.score ?? 0) + score });
  };
  const useful = (w: string) => !STOPWORDS.has(norm(w)) && (w.length >= 4 || isTechy(w));
  tokens.forEach((w, i) => {
    if (!useful(w)) return;
    bump(w, isTechy(w) ? 3 : properNoun(i) ? 2 : 1);
    const next = tokens[i + 1];
    if (next && useful(next) && !isTechy(w) && !isTechy(next)) bump(`${w} ${next}`, 0.8);
  });
  return [...scores.values()]
    .filter((s) => s.score >= 2)
    .sort((a, b) => b.score - a.score)
    .slice(0, max)
    .map((s) => s.label);
}

/** All the CV text the ATS would read (included items of enabled sections only). */
export function cvText(cv: CV): string {
  const p = cv.profile;
  const parts: string[] = [p.basics.headline, cv.settings.sections.includes("summary") ? p.basics.summary : ""];
  for (const k of LIST_KEYS) {
    if (!cv.settings.sections.includes(k)) continue;
    for (const it of p[k]) {
      if (!it.include) continue;
      for (const v of Object.values(it)) parts.push(Array.isArray(v) ? v.join(" ") : typeof v === "string" ? v : "");
    }
  }
  return norm(parts.join(" \n "));
}

export function targetKeywords(cv: CV): string[] {
  const t = cv.settings.target;
  return t.keywords.length ? t.keywords : extractKeywords(t.offer_text, 15);
}

export function keywordMatch(cv: CV) {
  const keywords = targetKeywords(cv);
  const text = cvText(cv);
  const found = keywords.filter((k) => text.includes(norm(k)));
  const missing = keywords.filter((k) => !text.includes(norm(k)));
  return { keywords, found, missing, percent: keywords.length ? Math.round((100 * found.length) / keywords.length) : null };
}

export interface Check {
  label: string;
  ok: boolean;
  hint: string;
}

export function qualityChecks(cv: CV): { score: number; checks: Check[] } {
  const p = cv.profile;
  const exp = p.experience.filter((e) => e.include);
  const skills = p.skills.filter((s) => s.include);
  const match = keywordMatch(cv);
  const t = cv.settings.target;
  const checks: Check[] = [
    { label: "Nom et titre", ok: Boolean(p.basics.full_name && p.basics.headline), hint: "Renseignez votre nom et un titre clair." },
    { label: "Email et téléphone", ok: Boolean(p.basics.email && p.basics.phone), hint: "Le recruteur doit pouvoir vous joindre." },
    { label: "Résumé de 3 à 5 phrases", ok: p.basics.summary.trim().length >= 200, hint: "Au moins 200 caractères, avec vos mots-clés." },
    { label: "Expériences décrites", ok: exp.length > 0 && exp.every((e) => String(e.description).trim().length >= 40), hint: "Chaque expérience retenue a besoin d'une description." },
    { label: "Puces et verbes d'action", ok: exp.some((e) => /^\s*[-•]/m.test(String(e.description))), hint: "Une puce « - » par réalisation." },
    { label: "Au moins 8 compétences", ok: skills.length >= 8, hint: `${skills.length} retenue(s) pour l'instant.` },
    { label: "Formation", ok: p.education.some((e) => e.include), hint: "Ajoutez au moins une formation." },
    { label: "Poste visé renseigné", ok: Boolean(t.title || t.offer_text.trim()), hint: "Indiquez le poste ou collez l'offre." },
  ];
  if (match.percent !== null)
    checks.push({ label: "Mots-clés de l'offre couverts (60 %)", ok: match.percent >= 60, hint: `${match.percent} % couverts.` });
  const score = Math.round((100 * checks.filter((c) => c.ok).length) / checks.length);
  return { score, checks };
}
