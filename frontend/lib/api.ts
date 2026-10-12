import type { AgentName, AgentResult, ChatMessage, CV, Job, LLMConfig, Profile, Suggestions } from "./types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function call<T>(path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API + path, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error(`Le serveur ne répond pas sur ${API}. Lancez le backend (voir README).`);
  }
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    const detail = data?.detail;
    throw new Error(typeof detail === "string" ? detail : `Erreur ${res.status}`);
  }
  return res.json();
}

export const api = {
  startScrape: (b: { profile_url: string; email: string; password: string; show_browser: boolean }) =>
    call<Job>("/api/scrape", b),
  job: <R = Profile>(id: string) => call<Job<R>>(`/api/jobs/${id}`),
  sendCode: (id: string, code: string) => call(`/api/jobs/${id}/code`, { code }),
  startAgent: (b: { llm: LLMConfig; cv: CV; instruction: string; history: ChatMessage[] }) =>
    call<Job<AgentResult>>("/api/agent", b),
  importOffer: (url: string) => call<{ text: string }>("/api/offer", { url }),
  testLLM: (llm: LLMConfig) => call<{ reply: string }>("/api/llm/test", llm),
  enhance: (b: { llm: LLMConfig; cv: CV; job_description: string; agents: AgentName[] }) =>
    call<Suggestions>("/api/enhance", b),
  async exportFile(cv: CV, fmt: "pdf" | "docx"): Promise<{ blob: Blob; filename: string }> {
    let res: Response;
    try {
      res = await fetch(`${API}/api/export/${fmt}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cv),
      });
    } catch {
      throw new Error(`Le serveur ne répond pas sur ${API}.`);
    }
    if (!res.ok) throw new Error(`Export impossible (${res.status})`);
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
