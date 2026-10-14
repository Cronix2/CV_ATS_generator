"use client";

import {
  Bot, BrainCircuit, ChevronDown, CircleCheck, FileText, Globe, Languages, ListChecks, PenLine, RotateCcw,
  ScanSearch, Search, Send, Sparkles, Target, WandSparkles, Wrench, type LucideIcon,
} from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { api } from "@/lib/api";
import { normalizeCV, useStore } from "@/lib/store";
import type { AgentChange, AgentResult, ChatMessage, CV } from "@/lib/types";
import { SuggestionsPanel } from "./SuggestionsPanel";
import { Alert, Button, Spinner, Textarea } from "./ui";

const QUICK_ACTIONS: { label: string; Icon: LucideIcon; prompt: string }[] = [
  { label: "Adapter au poste visé", Icon: Target, prompt: "Adapte tout le CV au poste visé : titre, résumé, descriptions d'expérience, compétences et mots-clés de l'offre. Masque ce qui n'est pas pertinent pour ce poste." },
  { label: "Rechercher les attentes du poste", Icon: Search, prompt: "Fais une recherche web sur les compétences et mots-clés attendus pour le poste visé, enregistre les mots-clés importants, puis ajoute à mes compétences celles que mon CV démontre déjà." },
  { label: "Réécrire mes expériences", Icon: PenLine, prompt: "Réécris les descriptions de mes expériences retenues : 3 à 5 puces chacune, verbes d'action, résultats concrets, mots-clés du poste visé." },
  { label: "Rédiger titre et résumé", Icon: FileText, prompt: "Rédige un titre professionnel ciblé et un résumé de 3 à 5 phrases aligné sur le poste visé." },
  { label: "Audit ATS et corrections", Icon: ListChecks, prompt: "Lance un audit ATS du CV, corrige toi-même tout ce qui peut l'être, puis liste ce que je dois compléter." },
  { label: "Corriger l'extraction", Icon: Wrench, prompt: "Vérifie les données extraites de LinkedIn : corrige les champs mal découpés (intitulé, entreprise, lieu, type de contrat, diplôme, domaine), les doublons et les incohérences de dates." },
  { label: "Traduire en anglais", Icon: Languages, prompt: "Traduis tout le contenu du CV en anglais professionnel et passe les intitulés de sections en anglais." },
];

const FEED_ICONS: Record<string, { Icon: LucideIcon; color: string }> = {
  think: { Icon: BrainCircuit, color: "var(--color-ai)" },
  search: { Icon: Globe, color: "#0e7490" },
  read: { Icon: FileText, color: "#0e7490" },
  agent: { Icon: Bot, color: "var(--color-ai)" },
  cv: { Icon: ScanSearch, color: "var(--color-muted)" },
  edit: { Icon: PenLine, color: "var(--color-brand)" },
  done: { Icon: CircleCheck, color: "var(--color-ok)" },
};

const SECTION_NAMES: Record<string, string> = {
  basics: "En-tête", experience: "Expérience", education: "Formation", skills: "Compétences",
  certifications: "Certification", languages: "Langue", projects: "Projet", volunteering: "Bénévolat",
  honors: "Distinction", publications: "Publication", courses: "Cours", settings: "Réglages",
};
const ACTION_NAMES: Record<AgentChange["action"], string> = {
  update: "modifié", add: "ajouté", delete: "supprimé", show: "affiché", hide: "masqué",
};

interface Turn {
  user: string;
  feed: string[];
  status: "running" | "done" | "error";
  reply?: string;
  error?: string;
  changes?: AgentChange[];
  before?: CV; // CV before this turn, to restore it
  restored?: boolean;
}

const show = (v: unknown) =>
  v === null || v === undefined ? "—" : typeof v === "string" ? v || "—" : Array.isArray(v) ? v.join(", ") : JSON.stringify(v, null, 1);

function FeedLine({ raw }: { raw: string }) {
  const [kind, ...rest] = raw.split("::");
  const text = rest.join("::") || kind;
  const { Icon, color } = FEED_ICONS[rest.length ? kind : "think"] ?? FEED_ICONS.think;
  return (
    <li className="feed-in flex items-start gap-2 text-sm">
      <Icon className="mt-0.5 size-4 shrink-0" style={{ color }} aria-hidden />
      <span className="min-w-0 break-words text-muted">{text}</span>
    </li>
  );
}

function Changes({ changes }: { changes: AgentChange[] }) {
  if (!changes.length) return <p className="text-sm text-muted">Aucune modification du CV.</p>;
  return (
    <details className="group rounded-md border border-line">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-sm font-medium [&::-webkit-details-marker]:hidden">
        <PenLine className="size-4 text-brand" aria-hidden />
        {changes.length} modification{changes.length > 1 ? "s" : ""} du CV
        <ChevronDown className="ml-auto size-4 text-muted transition-transform group-open:rotate-180" aria-hidden />
      </summary>
      <ul className="divide-y divide-line/70 border-t border-line">
        {changes.map((c, i) => (
          <li key={i} className="px-3 py-2 text-sm">
            <p>
              <span className="mr-1.5 rounded bg-brand-soft px-1.5 py-0.5 text-xs font-medium text-brand">{SECTION_NAMES[c.section] ?? c.section}</span>
              {c.label} <span className="text-muted">— {ACTION_NAMES[c.action]}</span>
            </p>
            {c.action === "update" && (
              <div className="mt-1.5 grid gap-2 text-xs md:grid-cols-2">
                <p className="whitespace-pre-line rounded bg-danger/5 p-2 text-muted line-through decoration-danger/30">{show(c.before)}</p>
                <p className="whitespace-pre-line rounded bg-ok/5 p-2">{show(c.after)}</p>
              </div>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}

function AgentPanel() {
  const { cv, update, checkpoint, llm, server } = useStore();
  const model = llm.api_key.trim() ? llm.model : server?.llm.model;
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [jobId, setJobId] = useState("");
  const [error, setError] = useState("");
  const bottom = useRef<HTMLDivElement>(null);
  const running = Boolean(jobId);
  const target = cv.settings.target;

  const patchLast = (patch: Partial<Turn>) => setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, ...patch } : x)));

  // Poll the running job: live activity feed, then apply the agent's CV.
  useEffect(() => {
    if (!jobId) return;
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const job = await api.job<AgentResult>(jobId);
        if (stop) return;
        if (job.status === "done" && job.result) {
          const result = job.result;
          checkpoint("modifications de l'agent IA");
          update(() => normalizeCV(result.cv));
          patchLast({ status: "done", feed: job.messages, reply: result.reply, changes: result.changes });
          setJobId("");
        } else if (job.status === "error") {
          patchLast({ status: "error", feed: job.messages, error: job.error });
          setJobId("");
        } else {
          patchLast({ feed: job.messages });
          timer = setTimeout(poll, 1200);
        }
      } catch (err) {
        if (!stop) {
          patchLast({ status: "error", error: (err as Error).message });
          setJobId("");
        }
      }
    };
    poll();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "nearest" }); // no return: may be a Promise in recent browsers
  }, [turns]);

  async function send(text: string) {
    const instruction = text.trim();
    if (!instruction || running) return;
    setError("");
    const history: ChatMessage[] = turns.flatMap((t) =>
      t.reply ? [{ role: "user" as const, content: t.user }, { role: "assistant" as const, content: t.reply }] : [],
    );
    try {
      const job = await api.startAgent({ llm, cv, instruction, history });
      setTurns((t) => [...t, { user: instruction, feed: [], status: "running", before: cv }]);
      setInput("");
      setJobId(job.id);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const restore = (i: number) => {
    const before = turns[i].before;
    if (!before) return;
    checkpoint("restauration avant l'agent");
    update(() => before);
    setTurns((t) => t.map((x, j) => (j === i ? { ...x, restored: true } : x)));
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) send(input);
  };

  return (
    <div className="space-y-4">
      {!target.title && !target.offer_text.trim() && (
        <Alert tone="info">
          Renseignez le <strong>poste visé</strong> à l&apos;étape « Tri et édition » : l&apos;agent s&apos;en sert pour cibler le CV.
        </Alert>
      )}

      <section className="rounded-lg border border-line bg-white p-4">
        <p className="mb-2 text-[13px] font-medium">Actions rapides</p>
        <div className="flex flex-wrap gap-2">
          {QUICK_ACTIONS.map((a) => (
            <button
              key={a.label}
              type="button"
              disabled={running}
              onClick={() => send(a.prompt)}
              className="inline-flex items-center gap-1.5 rounded-full border border-ai/25 bg-ai-soft px-3 py-1.5 text-sm text-ai transition-colors hover:border-ai hover:bg-ai hover:text-white disabled:opacity-50"
            >
              <a.Icon className="size-4" aria-hidden /> {a.label}
            </button>
          ))}
        </div>
      </section>

      {turns.length > 0 && (
        <ol className="space-y-4" aria-live="polite">
          {turns.map((t, i) => (
            <li key={i} className="space-y-2">
              <p className="ml-auto w-fit max-w-[85%] whitespace-pre-line rounded-lg rounded-br-sm bg-brand px-3 py-2 text-sm text-white">{t.user}</p>
              <div className="space-y-3 rounded-lg rounded-bl-sm border border-ai/20 bg-white p-4">
                <div className="flex items-center gap-2 text-sm font-medium text-ai">
                  <Bot className="size-4" aria-hidden /> Agent
                  {t.status === "running" && <Spinner />}
                </div>
                {t.feed.length > 0 && (
                  <ol className="space-y-1.5 border-l-2 border-ai/20 pl-3">
                    {t.feed.map((m, j) => <FeedLine key={j} raw={m} />)}
                  </ol>
                )}
                {t.status === "error" && <Alert>{t.error}</Alert>}
                {t.reply && <p className="whitespace-pre-line text-sm leading-relaxed">{t.reply}</p>}
                {t.changes && <Changes changes={t.changes} />}
                {t.status === "done" && t.changes && t.changes.length > 0 && (
                  <Button variant="secondary" disabled={t.restored} onClick={() => restore(i)}>
                    <RotateCcw className="size-4" aria-hidden /> {t.restored ? "Version précédente restaurée" : "Restaurer le CV d'avant"}
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
      <div ref={bottom} />

      <section className="rounded-lg border border-ai/30 bg-white p-3 shadow-sm">
        <Textarea
          rows={3}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKey}
          disabled={running}
          aria-label="Demande à l'agent"
          placeholder="Demandez ce que vous voulez : « mets en avant mes projets cybersécurité », « raccourcis le CV à une page »…"
          className="border-0 focus:ring-0"
        />
        {error && <div className="mt-2"><Alert>{error}</Alert></div>}
        <div className="mt-2 flex items-center justify-between gap-2">
          <span className="text-xs text-muted">Ctrl + Entrée pour envoyer · modèle : {model}</span>
          <Button variant="ai" disabled={running || !input.trim()} onClick={() => send(input)}>
            {running ? <Spinner /> : <Send className="size-4" aria-hidden />} {running ? "L'agent travaille…" : "Envoyer"}
          </Button>
        </div>
      </section>
    </div>
  );
}

export function AIStep() {
  const { aiReady, setStep } = useStore();
  const [tab, setTab] = useState<"agent" | "suggestions">("agent");

  if (!aiReady)
    return (
      <div className="space-y-3">
        <h1 className="text-2xl font-semibold tracking-tight">Agent IA</h1>
        <Alert tone="ai">Ajoutez une clé d&apos;API sur l&apos;écran de connexion pour activer l&apos;agent.</Alert>
        <div className="flex gap-3">
          <Button variant="secondary" onClick={() => setStep("connect")}>Ajouter une clé</Button>
          <Button variant="ghost" onClick={() => setStep("export")}>Passer à l&apos;export</Button>
        </div>
      </div>
    );

  const tabs = [
    { id: "agent" as const, label: "Agent", Icon: Sparkles, help: "Recherche web, outils, modifie le CV directement" },
    { id: "suggestions" as const, label: "Propositions", Icon: WandSparkles, help: "Sans outils, vous validez chaque proposition" },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Agent IA</h1>
          <p className="mt-1 text-sm text-muted">
            Un agent superviseur pilote un sous-agent chercheur (web) et un sous-agent auditeur ATS, puis modifie le CV. Tout reste annulable.
          </p>
        </div>
        <Button onClick={() => setStep("export")}>Passer à l&apos;export</Button>
      </div>
      <div role="tablist" className="grid gap-2 sm:grid-cols-2">
        {tabs.map((t) => (
          <button
            key={t.id}
            role="tab"
            type="button"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-3 rounded-lg border px-4 py-3 text-left transition-colors ${
              tab === t.id ? "border-ai bg-ai-soft" : "border-line bg-white hover:border-ai/40"
            }`}
          >
            <t.Icon className={`size-5 ${tab === t.id ? "text-ai" : "text-muted"}`} aria-hidden />
            <span>
              <span className="block text-sm font-semibold">{t.label}</span>
              <span className="block text-xs text-muted">{t.help}</span>
            </span>
          </button>
        ))}
      </div>
      {/* Both stay mounted so a running agent or loaded proposals survive tab switches. */}
      <div hidden={tab !== "agent"}><AgentPanel /></div>
      <div hidden={tab !== "suggestions"}><SuggestionsPanel /></div>
    </div>
  );
}
