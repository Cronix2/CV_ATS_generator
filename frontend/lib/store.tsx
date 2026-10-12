"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import {
  ALL_SECTIONS, LIST_KEYS, emptyCV, emptyProfile, emptyTarget, newId,
  type CV, type Item, type LLMConfig, type Profile,
} from "./types";

export type Step = "connect" | "scrape" | "edit" | "ai" | "export";

interface Snapshot {
  cv: CV;
  label: string;
}

interface Store {
  cv: CV;
  update: (fn: (cv: CV) => CV) => void;
  /** Saves the current CV so the next big change (AI, deletion, import…) can be undone. */
  checkpoint: (label: string) => void;
  undo: () => void;
  lastCheckpoint: string | null;
  llm: LLMConfig;
  setLlm: (llm: LLMConfig) => void;
  step: Step;
  setStep: (s: Step) => void;
  jobId: string;
  setJobId: (id: string) => void;
}

const Ctx = createContext<Store | null>(null);
const CV_KEY = "cv-ats:cv";
const LLM_KEY = "cv-ats:llm";
const MAX_HISTORY = 25;

/** Accepts a scraped profile, a saved CV, or partial JSON and returns a complete CV. */
export function normalizeCV(data: unknown): CV {
  const raw = (data ?? {}) as Partial<CV> & Partial<Profile>;
  const profile = (raw.profile ?? raw) as Partial<Profile>;
  const base = emptyProfile();
  const defaults = emptyCV().settings;
  const settings = { ...defaults, ...(raw.settings ?? {}) };
  const out: CV = {
    profile: { ...base, basics: { ...base.basics, ...(profile.basics ?? {}) } },
    settings: { ...settings, target: { ...emptyTarget(), ...(settings.target ?? {}) } },
  };
  for (const k of LIST_KEYS) {
    out.profile[k] = (Array.isArray(profile[k]) ? profile[k] : []).map((it: Item) => ({
      ...it, id: it.id || newId(), include: it.include ?? true,
    }));
  }
  out.settings.sections = out.settings.sections.filter((s) => ALL_SECTIONS.includes(s));
  if (!/^#[0-9a-f]{6}$/i.test(out.settings.accent)) out.settings.accent = defaults.accent;
  return out;
}

function load<T>(storage: () => Storage, key: string): T | null {
  try {
    const v = storage().getItem(key);
    return v ? (JSON.parse(v) as T) : null;
  } catch {
    return null;
  }
}
function save(storage: () => Storage, key: string, value: unknown) {
  try {
    storage().setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable: state just won't survive a reload */
  }
}

export function StoreProvider({ children }: { children: ReactNode }) {
  const [cv, setCv] = useState<CV>(emptyCV);
  const [history, setHistory] = useState<Snapshot[]>([]);
  const [llm, setLlmState] = useState<LLMConfig>({ api_key: "", base_url: "", model: "gpt-4o-mini" });
  const [step, setStep] = useState<Step>("connect");
  const [jobId, setJobId] = useState("");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const savedCv = load<CV>(() => localStorage, CV_KEY);
    if (savedCv) setCv(normalizeCV(savedCv));
    // The API key stays in sessionStorage: forgotten when the tab is closed.
    const savedLlm = load<LLMConfig>(() => sessionStorage, LLM_KEY);
    if (savedLlm) setLlmState(savedLlm);
    setReady(true);
  }, []);

  useEffect(() => {
    if (ready) save(() => localStorage, CV_KEY, cv);
  }, [cv, ready]);

  const setLlm = (v: LLMConfig) => {
    setLlmState(v);
    save(() => sessionStorage, LLM_KEY, v);
  };

  const checkpoint = useCallback(
    (label: string) => setHistory((h) => [...h.slice(-(MAX_HISTORY - 1)), { cv, label }]),
    [cv],
  );
  const undo = useCallback(() => {
    setHistory((h) => {
      const last = h.at(-1);
      if (last) setCv(last.cv);
      return h.slice(0, -1);
    });
  }, []);

  return (
    <Ctx.Provider
      value={{
        cv, update: setCv, checkpoint, undo, lastCheckpoint: history.at(-1)?.label ?? null,
        llm, setLlm, step, setStep, jobId, setJobId,
      }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useStore() {
  const s = useContext(Ctx);
  if (!s) throw new Error("useStore outside StoreProvider");
  return s;
}

export function hasContent(cv: CV) {
  return Boolean(cv.profile.basics.full_name || LIST_KEYS.some((k) => cv.profile[k].length));
}
