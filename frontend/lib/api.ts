import { apiBase, wsUrl } from "./apiBase";
import type { AgentName, AgentResult, ChatMessage, CV, Job, LLMConfig, Profile, ServerConfig, Suggestions } from "./types";

const API = apiBase(process.env.NEXT_PUBLIC_API_URL); // origin only: routes below already start with /api/

// Access token (only when the server sets PASSEFILTRE_TOKEN). Kept in memory + sessionStorage by the store.
let apiToken = "";
export const setApiToken = (token: string) => {
  apiToken = token.trim();
};
const authHeaders = (): Record<string, string> => (apiToken ? { "X-PasseFiltre-Token": apiToken } : {});

// Owner key of each job started from this tab (memory only): the server refuses job calls without it.
const jobKeys = new Map<string, string>();
function remember<J extends Job<unknown>>(job: J): J {
  if (job.key) jobKeys.set(job.id, job.key);
  return job;
}
const jobHeaders = (id: string): Record<string, string> => ({ "X-PasseFiltre-Job-Key": jobKeys.get(id) ?? "" });

function httpError(status: number, detail: unknown): Error {
  if (status === 401) return new Error("Jeton d'accès manquant ou invalide : saisissez-le sur l'écran de connexion.");
  return new Error(typeof detail === "string" ? detail : `Erreur ${status}`);
}

async function call<T>(path: string, body?: unknown, extra: { method?: string; headers?: Record<string, string> } = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API + path, {
      method: extra.method ?? (body === undefined ? "GET" : "POST"),
      headers: { ...authHeaders(), ...extra.headers, ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error(`Le serveur ne répond pas sur ${API}. Lancez le backend (voir README).`);
  }
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw httpError(res.status, data?.detail);
  }
  return res.json();
}

export const api = {
  startScrape: (b: { profile_url: string; email: string; password: string; show_browser: boolean }) =>
    call<Job>("/api/scrape", b).then(remember),
  job: <R = Profile>(id: string) => call<Job<R>>(`/api/jobs/${id}`, undefined, { headers: jobHeaders(id) }),
  sendCode: (id: string, code: string) => call(`/api/jobs/${id}/code`, { code }, { headers: jobHeaders(id) }),
  cancelJob: (id: string) => call(`/api/jobs/${id}`, undefined, { method: "DELETE", headers: jobHeaders(id) }),
  /** Single-use ticket for the CAPTCHA viewer WebSocket (sent as a sub-protocol, never in the URL). */
  captchaTicket: (id: string) =>
    call<{ ticket: string; protocol: string; expires_in: number }>(`/api/jobs/${id}/captcha/ticket`, {}, { headers: jobHeaders(id) }),
  captchaSocketUrl: (id: string) => wsUrl(API, `/api/jobs/${id}/captcha/vnc`),
  startAgent: (b: { llm: LLMConfig; cv: CV; instruction: string; history: ChatMessage[] }) =>
    call<Job<AgentResult>>("/api/agent", b).then(remember),
  importOffer: (url: string) => call<{ text: string }>("/api/offer", { url }),
  forgetLinkedInSession: (b: { email: string; password: string }) =>
    call<{ removed: boolean }>("/api/linkedin/logout", b),
  config: () => call<ServerConfig>("/api/config"),
  testLLM: (llm: LLMConfig) => call<{ reply: string }>("/api/llm/test", llm),
  enhance: (b: { llm: LLMConfig; cv: CV; job_description: string; agents: AgentName[] }) =>
    call<Suggestions>("/api/enhance", b),
  async exportFile(cv: CV, fmt: "pdf" | "docx"): Promise<{ blob: Blob; filename: string }> {
    let res: Response;
    try {
      res = await fetch(`${API}/api/export/${fmt}`, {
        method: "POST",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify(cv),
      });
    } catch {
      throw new Error(`Le serveur ne répond pas sur ${API}.`);
    }
    if (!res.ok) throw res.status === 401 ? httpError(401, null) : new Error(`Export impossible (${res.status})`);
    const name = res.headers.get("Content-Disposition")?.match(/filename="(.+)"/)?.[1] ?? `CV.${fmt}`;
    return { blob: await res.blob(), filename: name };
  },
};

export function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
