import {
  Award, BookOpen, Briefcase, FileText, FolderGit2, GraduationCap, HeartHandshake, Languages, Library,
  Trophy, Wrench, type LucideIcon,
} from "lucide-react";
import { newId, type Item, type ListKey, type SectionKey } from "./types";

/** Each section has its own colour + icon so the long editor stays scannable. */
export const SECTION_STYLE: Record<SectionKey, { color: string; Icon: LucideIcon }> = {
  summary: { color: "#2557d6", Icon: FileText },
  experience: { color: "#1d4ed8", Icon: Briefcase },
  education: { color: "#0f8a7e", Icon: GraduationCap },
  skills: { color: "#c26a06", Icon: Wrench },
  certifications: { color: "#7c3aed", Icon: Award },
  languages: { color: "#c0267a", Icon: Languages },
  projects: { color: "#d4550b", Icon: FolderGit2 },
  volunteering: { color: "#15803d", Icon: HeartHandshake },
  honors: { color: "#a16207", Icon: Trophy },
  publications: { color: "#475569", Icon: BookOpen },
  courses: { color: "#0e7490", Icon: Library },
};

export type FieldType = "text" | "textarea" | "tags" | "bool";
export interface FieldDef {
  key: string;
  label: string;
  type?: FieldType;
  wide?: boolean;
  placeholder?: string;
}

interface SectionDef {
  label: string;
  fields: FieldDef[];
  /** Line shown when the item is collapsed. */
  title: (it: Item) => string;
}

const s = (v: unknown) => (typeof v === "string" ? v : "");
const join = (...parts: unknown[]) => parts.map(s).filter(Boolean).join(" — ");
const dates: FieldDef[] = [
  { key: "start", label: "Début", placeholder: "MM/AAAA" },
  { key: "end", label: "Fin", placeholder: "MM/AAAA" },
];

export const SECTION_LABELS: Record<SectionKey, string> = {
  summary: "Résumé",
  experience: "Expériences",
  education: "Formations",
  skills: "Compétences",
  certifications: "Certifications",
  languages: "Langues",
  projects: "Projets",
  volunteering: "Bénévolat",
  honors: "Distinctions",
  publications: "Publications",
  courses: "Cours",
};

export const SECTIONS: Record<ListKey, SectionDef> = {
  experience: {
    label: SECTION_LABELS.experience,
    title: (it) => join(it.title, it.company),
    fields: [
      { key: "title", label: "Intitulé du poste" },
      { key: "company", label: "Entreprise" },
      { key: "employment_type", label: "Type de contrat" },
      { key: "location", label: "Lieu" },
      ...dates,
      { key: "current", label: "Poste actuel", type: "bool" },
      { key: "description", label: "Description (une puce par ligne, commencez par « - »)", type: "textarea", wide: true },
      { key: "skills", label: "Compétences associées (séparées par des virgules)", type: "tags", wide: true },
    ],
  },
  education: {
    label: SECTION_LABELS.education,
    title: (it) => join(it.degree || it.school, it.degree ? it.school : ""),
    fields: [
      { key: "school", label: "Établissement" },
      { key: "degree", label: "Diplôme" },
      { key: "field", label: "Domaine" },
      { key: "grade", label: "Mention" },
      ...dates,
      { key: "description", label: "Description", type: "textarea", wide: true },
    ],
  },
  skills: {
    label: SECTION_LABELS.skills,
    title: (it) => s(it.name),
    fields: [{ key: "name", label: "Compétence" }],
  },
  certifications: {
    label: SECTION_LABELS.certifications,
    title: (it) => join(it.name, it.issuer),
    fields: [
      { key: "name", label: "Nom" },
      { key: "issuer", label: "Organisme" },
      { key: "issued", label: "Obtenue le", placeholder: "MM/AAAA" },
      { key: "expires", label: "Expire le", placeholder: "MM/AAAA" },
      { key: "credential_id", label: "ID de certification" },
      { key: "url", label: "Lien" },
    ],
  },
  languages: {
    label: SECTION_LABELS.languages,
    title: (it) => join(it.name, it.proficiency),
    fields: [
      { key: "name", label: "Langue" },
      { key: "proficiency", label: "Niveau", placeholder: "Courant, C1…" },
    ],
  },
  projects: {
    label: SECTION_LABELS.projects,
    title: (it) => s(it.name),
    fields: [
      { key: "name", label: "Nom" },
      { key: "url", label: "Lien" },
      ...dates,
      { key: "description", label: "Description", type: "textarea", wide: true },
      { key: "skills", label: "Technologies (séparées par des virgules)", type: "tags", wide: true },
    ],
  },
  volunteering: {
    label: SECTION_LABELS.volunteering,
    title: (it) => join(it.role, it.organization),
    fields: [
      { key: "role", label: "Rôle" },
      { key: "organization", label: "Organisation" },
      { key: "cause", label: "Cause" },
      ...dates,
      { key: "current", label: "En cours", type: "bool" },
      { key: "description", label: "Description", type: "textarea", wide: true },
    ],
  },
  honors: {
    label: SECTION_LABELS.honors,
    title: (it) => join(it.title, it.issuer),
    fields: [
      { key: "title", label: "Titre" },
      { key: "issuer", label: "Décerné par" },
      { key: "date", label: "Date", placeholder: "MM/AAAA" },
      { key: "description", label: "Description", type: "textarea", wide: true },
    ],
  },
  publications: {
    label: SECTION_LABELS.publications,
    title: (it) => join(it.title, it.publisher),
    fields: [
      { key: "title", label: "Titre" },
      { key: "publisher", label: "Éditeur" },
      { key: "date", label: "Date", placeholder: "MM/AAAA" },
      { key: "url", label: "Lien" },
      { key: "description", label: "Description", type: "textarea", wide: true },
    ],
  },
  courses: {
    label: SECTION_LABELS.courses,
    title: (it) => join(it.name, it.number),
    fields: [
      { key: "name", label: "Intitulé" },
      { key: "number", label: "Code" },
    ],
  },
};

export function newItem(key: ListKey): Item {
  const item: Item = { id: newId(), include: true };
  for (const f of SECTIONS[key].fields) item[f.key] = f.type === "bool" ? false : f.type === "tags" ? [] : "";
  return item;
}
