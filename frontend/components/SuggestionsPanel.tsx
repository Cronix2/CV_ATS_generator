"use client";

import { useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import { newItem } from "@/lib/sections";
import { useStore } from "@/lib/store";
import type { AgentError, AgentName, Item, ListKey, Suggestions } from "@/lib/types";
import { Alert, Button, Spinner } from "./ui";

const AGENTS: { id: AgentName; label: string; help: string }[] = [
  { id: "ats_review", label: "Audit ATS", help: "Score de compatibilité, points forts, mots-clés manquants." },
  { id: "summary", label: "Titre et résumé", help: "Un titre ciblé et un résumé de 3 à 5 phrases." },
  { id: "experience", label: "Descriptions d'expériences", help: "Puces avec verbes d'action et mots-clés du métier." },
  { id: "skills", label: "Compétences", help: "Dédoublonnage, noms standards, tri par pertinence." },
  { id: "cleanup", label: "Correction de l'extraction", help: "Remet en ordre les champs mal découpés (poste, entreprise, lieu…)." },
];

const FIELD_LABELS: Record<string, string> = {
  title: "Poste", company: "Entreprise", location: "Lieu", employment_type: "Contrat",
  school: "Établissement", degree: "Diplôme", field: "Domaine",
};

const isError = (v: unknown): v is AgentError => typeof v === "object" && v !== null && "error" in v;

function Card({ title, children, actions }: { title: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="rounded-lg border border-line bg-white">
      <header className="flex flex-wrap items-center gap-2 border-b border-line/70 px-4 py-3">
        <h2 className="text-base font-semibold">{title}</h2>
        <div className="ml-auto flex gap-2">{actions}</div>
      </header>
      <div className="space-y-3 p-4 text-sm">{children}</div>
    </section>
  );
}

function Proposal({ before, after, onApply, applied }: { before: string; after: string; onApply: () => void; applied: boolean }) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <div>
        <p className="mb-1 text-xs text-muted">Actuel</p>
        <p className="whitespace-pre-line text-muted">{before || "—"}</p>
      </div>
      <div>
        <p className="mb-1 text-xs text-muted">Proposé</p>
        <p className="whitespace-pre-line">{after}</p>
        <Button variant="secondary" className="mt-2" disabled={applied} onClick={onApply}>
          {applied ? "Appliqué" : "Appliquer"}
        </Button>
      </div>
    </div>
  );
}

/** Structured assistants without tools: works with any model, even those without tool calling. */
export function SuggestionsPanel() {
  const { cv, update: rawUpdate, checkpoint, llm } = useStore();
  const [agents, setAgents] = useState<AgentName[]>(AGENTS.map((a) => a.id));
  const [result, setResult] = useState<Suggestions | null>(null);
  const [applied, setApplied] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // Every accepted proposal can be undone from the header.
  const update: typeof rawUpdate = (fn) => {
    checkpoint("proposition IA appliquée");
    rawUpdate(fn);
  };

  const mark = (key: string) => setApplied((s) => new Set(s).add(key));
  const patchItem = (section: ListKey, id: string, patch: Partial<Item>) =>
    update((c) => ({ ...c, profile: { ...c.profile, [section]: c.profile[section].map((x) => (x.id === id ? ({ ...x, ...patch } as Item) : x)) } }));

  async function run() {
    setBusy(true);
    setError("");
    try {
      setResult(await api.enhance({ llm, cv, job_description: "", agents })); // uses the target job
      setApplied(new Set());
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const r = result;
  const expById = new Map(cv.profile.experience.map((e) => [e.id, e]));
  const eduById = new Map(cv.profile.education.map((e) => [e.id, e]));

  return (
    <div className="space-y-4">
      <section className="space-y-4 rounded-lg border border-line bg-white p-4">
        <p className="text-sm text-muted">
          Des assistants spécialisés proposent des améliorations, alignées sur le poste visé. Rien n&apos;est modifié sans votre clic.
          Ce mode fonctionne avec tous les modèles, même sans appel d&apos;outils.
        </p>
        <fieldset className="grid gap-2 sm:grid-cols-2">
          <legend className="mb-2 text-sm font-medium">Assistants à lancer</legend>
          {AGENTS.map((a) => (
            <label key={a.id} className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-0.5 accent-ai"
                checked={agents.includes(a.id)}
                onChange={(e) => setAgents((s) => (e.target.checked ? [...s, a.id] : s.filter((x) => x !== a.id)))}
              />
              <span>
                {a.label}
                <span className="block text-xs text-muted">{a.help}</span>
              </span>
            </label>
          ))}
        </fieldset>
        {error && <Alert>{error}</Alert>}
        <Button variant="ai" disabled={busy || agents.length === 0} onClick={run}>
          {busy && <Spinner />} {busy ? "Les assistants travaillent…" : r ? "Relancer les assistants" : "Lancer les assistants"}
        </Button>
      </section>

      {r && (
        <>
          {Object.entries(r).filter(([, v]) => isError(v)).map(([k, v]) => (
            <Alert key={k}>{AGENTS.find((a) => a.id === k)?.label} : {(v as AgentError).error}</Alert>
          ))}

          {r.ats_review && !isError(r.ats_review) && (
            <Card title={`Audit ATS : ${r.ats_review.score}/100`}>
              {[["Points forts", r.ats_review.strengths], ["À améliorer", r.ats_review.improvements]].map(([label, list]) => (
                <div key={label as string}>
                  <p className="font-medium">{label as string}</p>
                  <ul className="mt-1 list-disc space-y-1 pl-5 text-muted">{(list as string[]).map((x, i) => <li key={i}>{x}</li>)}</ul>
                </div>
              ))}
            </Card>
          )}

          {r.summary && !isError(r.summary) && (
            <Card title="Titre et résumé">
              <Proposal before={cv.profile.basics.headline} after={r.summary.headline} applied={applied.has("headline")}
                onApply={() => { const headline = (r.summary as { headline: string }).headline; update((c) => ({ ...c, profile: { ...c.profile, basics: { ...c.profile.basics, headline } } })); mark("headline"); }} />
              <hr className="border-line/70" />
              <Proposal before={cv.profile.basics.summary} after={r.summary.summary} applied={applied.has("summary")}
                onApply={() => { const summary = (r.summary as { summary: string }).summary; update((c) => ({ ...c, profile: { ...c.profile, basics: { ...c.profile.basics, summary } } })); mark("summary"); }} />
            </Card>
          )}

          {r.experience && !isError(r.experience) && (
            <Card
              title="Descriptions d'expériences"
              actions={
                <Button variant="secondary" onClick={() => { for (const it of (r.experience as { items: { id: string; description: string }[] }).items) { patchItem("experience", it.id, { description: it.description }); mark(`exp-${it.id}`); } }}>
                  Tout appliquer
                </Button>
              }
            >
              {r.experience.items.filter((it) => expById.has(it.id)).map((it) => {
                const e = expById.get(it.id)!;
                return (
                  <div key={it.id} className="border-b border-line/70 pb-3 last:border-0">
                    <p className="mb-2 font-medium">{String(e.title)} — {String(e.company)}</p>
                    <Proposal before={String(e.description)} after={it.description} applied={applied.has(`exp-${it.id}`)}
                      onApply={() => { patchItem("experience", it.id, { description: it.description }); mark(`exp-${it.id}`); }} />
                  </div>
                );
              })}
            </Card>
          )}

          {r.skills && !isError(r.skills) && (
            <Card title="Compétences">
              <p className="text-muted">Liste proposée ({r.skills.skills.length}) :</p>
              <p>{r.skills.skills.join(", ")}</p>
              <Button variant="secondary" disabled={applied.has("skills")} onClick={() => {
                const names = (r.skills as { skills: string[] }).skills;
                update((c) => ({ ...c, profile: { ...c.profile, skills: names.map((name) => ({ ...newItem("skills"), name })) } }));
                mark("skills");
              }}>
                {applied.has("skills") ? "Appliqué" : "Remplacer mes compétences par cette liste"}
              </Button>
              {r.skills.missing_keywords.length > 0 && (
                <div className="pt-2">
                  <p className="font-medium">Mots-clés de l&apos;offre absents du profil</p>
                  <p className="text-xs text-muted">N&apos;ajoutez que ceux que vous maîtrisez vraiment.</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {r.skills.missing_keywords.map((k, i) => (
                      <Button key={i} variant="secondary" className="rounded-full py-1" disabled={applied.has(`kw-${k}`)}
                        onClick={() => { update((c) => ({ ...c, profile: { ...c.profile, skills: [...c.profile.skills, { ...newItem("skills"), name: k }] } })); mark(`kw-${k}`); }}>
                        + {k}
                      </Button>
                    ))}
                  </div>
                </div>
              )}
            </Card>
          )}

          {r.cleanup && !isError(r.cleanup) && (() => {
            const fixes = [
              ...r.cleanup.experience.filter((f) => expById.has(f.id)).map((f) => ({ section: "experience" as ListKey, f, cur: expById.get(f.id)! })),
              ...r.cleanup.education.filter((f) => eduById.has(f.id)).map((f) => ({ section: "education" as ListKey, f, cur: eduById.get(f.id)! })),
            ].map(({ section, f, cur }) => {
              const { id, ...fields } = f;
              const changes = Object.entries(fields).filter(([k, v]) => String(cur[k] ?? "") !== v);
              return { section, id, changes };
            }).filter((x) => x.changes.length);
            return (
              <Card title="Correction de l'extraction">
                {fixes.length === 0 ? <p className="text-muted">Aucune correction nécessaire.</p> : fixes.map(({ section, id, changes }) => (
                  <div key={id} className="flex flex-wrap items-start justify-between gap-2 border-b border-line/70 pb-3 last:border-0">
                    <ul className="space-y-0.5">
                      {changes.map(([k, v]) => (
                        <li key={k}><span className="text-muted">{FIELD_LABELS[k] ?? k} : </span><s className="text-muted">{String((section === "experience" ? expById : eduById).get(id)![k] || "—")}</s> → {v || "—"}</li>
                      ))}
                    </ul>
                    <Button variant="secondary" disabled={applied.has(`fix-${id}`)} onClick={() => { patchItem(section, id, Object.fromEntries(changes)); mark(`fix-${id}`); }}>
                      {applied.has(`fix-${id}`) ? "Appliqué" : "Appliquer"}
                    </Button>
                  </div>
                ))}
              </Card>
            );
          })()}
        </>
      )}
    </div>
  );
}
