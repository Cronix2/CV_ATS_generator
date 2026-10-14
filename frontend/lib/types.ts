// Mirror of backend/app/models.py

export type Value = string | boolean | string[];
export interface Item {
  id: string;
  include: boolean;
  [field: string]: Value;
}

export interface Basics {
  full_name: string;
  headline: string;
  location: string;
  email: string;
  phone: string;
  linkedin_url: string;
  websites: string[];
  summary: string;
}

export const LIST_KEYS = [
  "experience", "education", "skills", "certifications", "languages",
  "projects", "volunteering", "honors", "publications", "courses",
] as const;
export type ListKey = (typeof LIST_KEYS)[number];
export type SectionKey = "summary" | ListKey;
export const ALL_SECTIONS: SectionKey[] = ["summary", ...LIST_KEYS];

export type Profile = { basics: Basics } & Record<ListKey, Item[]>;

export interface Target {
  title: string;
  company: string;
  offer_url: string;
  offer_text: string;
  keywords: string[];
}

export interface CVSettings {
  language: "fr" | "en";
  sections: SectionKey[]; // enabled sections, in display order
  accent: string; // name + section titles colour in the exported CV
  target: Target;
}

export interface AgentChange {
  action: "update" | "add" | "delete" | "show" | "hide";
  section: string;
  label: string;
  before: unknown;
  after: unknown;
}

export interface AgentResult {
  reply: string;
  cv: CV;
  changes: AgentChange[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface CV {
  profile: Profile;
  settings: CVSettings;
}

export interface LLMConfig {
  api_key: string;
  base_url: string;
  model: string;
}

/** Server-side defaults (from the root .env). The API key itself is never sent to the browser. */
export interface ServerConfig {
  llm: { server_key: boolean; base_url: string; model: string };
  docker: boolean;
  auth_required: boolean;
}

export interface Job<R = Profile> {
  id: string;
  status: "running" | "needs_code" | "done" | "error";
  percent: number;
  messages: string[];
  prompt: string;
  error: string;
  result: R | null;
}

export type AgentName = "summary" | "experience" | "skills" | "cleanup" | "ats_review";
export type AgentError = { error: string };
export interface Suggestions {
  summary?: { headline: string; summary: string } | AgentError;
  experience?: { items: { id: string; description: string }[] } | AgentError;
  skills?: { skills: string[]; missing_keywords: string[] } | AgentError;
  cleanup?: {
    experience: { id: string; title: string; company: string; location: string; employment_type: string }[];
    education: { id: string; school: string; degree: string; field: string }[];
  } | AgentError;
  ats_review?: { score: number; strengths: string[]; improvements: string[]; missing_keywords: string[] } | AgentError;
}

export const newId = () => crypto.randomUUID().replace(/-/g, "").slice(0, 10);

export function emptyProfile(): Profile {
  const lists = Object.fromEntries(LIST_KEYS.map((k) => [k, [] as Item[]])) as Record<ListKey, Item[]>;
  return {
    basics: { full_name: "", headline: "", location: "", email: "", phone: "", linkedin_url: "", websites: [], summary: "" },
    ...lists,
  };
}

export const emptyTarget = (): Target => ({ title: "", company: "", offer_url: "", offer_text: "", keywords: [] });

export function emptyCV(): CV {
  return {
    profile: emptyProfile(),
    settings: { language: "fr", sections: [...ALL_SECTIONS], accent: "#111111", target: emptyTarget() },
  };
}
