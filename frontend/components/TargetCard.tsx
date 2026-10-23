"use client";

import { Link2, Target as TargetIcon, WandSparkles } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import { useATS } from "@/lib/ats";
import { useStore } from "@/lib/store";
import type { Target } from "@/lib/types";
import { Alert, Button, Card, Chip, Field, Input, Spinner, Textarea } from "./ui";

const COLOR = "#c2410c";

export function TargetCard() {
  const { cv, update } = useStore();
  const t = cv.settings.target;
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState("");
  const ats = useATS(cv);
  const match = ats.data ?? { keywords: t.keywords, found: [] as string[], missing: [] as string[], percent: null };

  const set = (patch: Partial<Target>) =>
    update((c) => ({ ...c, settings: { ...c.settings, target: { ...c.settings.target, ...patch } } }));

  async function importOffer() {
    setImporting(true);
    setError("");
    try {
      const { text } = await api.importOffer(t.offer_url);
      set({ offer_text: text });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setImporting(false);
    }
  }

  const addKeywords = () => {
    const extra = draft.split(",").map((s) => s.trim()).filter(Boolean);
    set({ keywords: [...new Set([...match.keywords, ...extra])] });
    setDraft("");
  };

  return (
    <Card
      Icon={TargetIcon}
      color={COLOR}
      title="Poste visé"
      aside={
        match.percent !== null && (
          <span className={`rounded-full px-2.5 py-0.5 text-sm font-semibold ${match.percent >= 60 ? "bg-ok/10 text-ok" : "bg-warn/10 text-warn"}`}>
            {match.percent} % des mots-clés
          </span>
        )
      }
    >
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Intitulé du poste">
            <Input value={t.title} onChange={(e) => set({ title: e.target.value })} placeholder="Pentester junior, Data Engineer…" />
          </Field>
          <Field label="Entreprise (facultatif)">
            <Input value={t.company} onChange={(e) => set({ company: e.target.value })} />
          </Field>
        </div>
        <Field label="Lien de l'offre (facultatif)" hint="Les offres LinkedIn demandent une connexion : collez plutôt leur texte ci-dessous.">
          <div className="flex gap-2">
            <Input type="url" value={t.offer_url} onChange={(e) => set({ offer_url: e.target.value })} placeholder="https://…" />
            <Button variant="secondary" disabled={!t.offer_url || importing} onClick={importOffer} className="shrink-0">
              {importing ? <Spinner /> : <Link2 className="size-4" aria-hidden />} Importer le texte
            </Button>
          </div>
        </Field>
        {error && <Alert>{error}</Alert>}
        {ats.error && <Alert>{ats.error}</Alert>}
        <Field label="Texte de l'offre">
          <Textarea rows={6} value={t.offer_text} onChange={(e) => set({ offer_text: e.target.value })} placeholder="Collez ici l'annonce : missions, profil recherché, compétences…" />
        </Field>

        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <p className="text-[13px] font-medium">Mots-clés de l&apos;offre</p>
            <span className="text-xs text-muted">
              {t.keywords.length ? "liste personnalisée" : match.keywords.length ? "suggérés automatiquement" : ""}
            </span>
            {t.offer_text && (
              <Button variant="ghost" className="ml-auto px-2 py-1 text-xs" disabled={!ats.data} onClick={() => set({ keywords: ats.data?.suggested_keywords ?? [] })}>
                <WandSparkles className="size-3.5" aria-hidden /> Réextraire
              </Button>
            )}
          </div>
          {match.keywords.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {match.keywords.map((k, i) => (
                <Chip key={i} tone={match.found.includes(k) ? "ok" : "missing"} onRemove={() => set({ keywords: match.keywords.filter((x) => x !== k) })}>
                  {match.found.includes(k) ? "✓" : "✗"} {k}
                </Chip>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted">Collez une offre ou ajoutez vos propres mots-clés.</p>
          )}
          <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); addKeywords(); }}>
            <Input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Ajouter : SIEM, Python, gestion de crise…" aria-label="Ajouter des mots-clés" />
            <Button type="submit" variant="secondary" disabled={!draft.trim()}>Ajouter</Button>
          </form>
          {match.missing.length > 0 && (
            <p className="mt-2 text-xs text-muted">
              En rouge : absents du CV. Ajoutez-les là où ils sont vrais (compétences, descriptions), ou demandez à l&apos;agent IA.
            </p>
          )}
        </div>
      </div>
    </Card>
  );
}
