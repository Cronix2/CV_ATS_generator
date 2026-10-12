"use client";

import { Download, FileDown, FileText, Palette } from "lucide-react";
import { useState } from "react";
import { api, download } from "@/lib/api";
import { useStore } from "@/lib/store";
import { Alert, Button, Spinner } from "./ui";

const ACCENTS = [
  { label: "Noir", value: "#111111" },
  { label: "Marine", value: "#1F3A68" },
  { label: "Bleu", value: "#1D4ED8" },
  { label: "Pétrole", value: "#0F5E66" },
  { label: "Vert", value: "#1E6B3A" },
  { label: "Bordeaux", value: "#7A1F2B" },
  { label: "Prune", value: "#5B2A6E" },
];

const CHECKS = [
  "Une seule colonne, sans tableau, image ni icône",
  "Texte réel et sélectionnable, police standard",
  "Intitulés de sections standards reconnus par les ATS",
  "Coordonnées dans le corps du document, pas en en-tête",
  "Puces simples et emojis retirés",
];

export function ExportStep() {
  const { cv, update } = useStore();
  const [busy, setBusy] = useState<"" | "pdf" | "docx">("");
  const [error, setError] = useState("");

  async function exportAs(fmt: "pdf" | "docx") {
    setBusy(fmt);
    setError("");
    try {
      const { blob, filename } = await api.exportFile(cv, fmt);
      download(blob, filename);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy("");
    }
  }

  const name = cv.profile.basics.full_name.trim().replace(/\s+/g, "-") || "cv";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Télécharger le CV</h1>
        <p className="mt-1 text-sm text-muted">Le PDF est celui de l&apos;aperçu. Le Word est utile quand un site de candidature le demande.</p>
      </div>

      <section className="space-y-4 rounded-lg border border-line bg-white p-5">
        <fieldset>
          <legend className="mb-2 text-sm font-medium">Langue des intitulés de sections</legend>
          <div className="flex gap-4 text-sm">
            {(["fr", "en"] as const).map((lang) => (
              <label key={lang} className="flex items-center gap-2">
                <input
                  type="radio"
                  name="lang"
                  className="accent-brand"
                  checked={cv.settings.language === lang}
                  onChange={() => update((c) => ({ ...c, settings: { ...c.settings, language: lang } }))}
                />
                {lang === "fr" ? "Français" : "Anglais"}
              </label>
            ))}
          </div>
        </fieldset>
        <fieldset>
          <legend className="mb-2 flex items-center gap-2 text-sm font-medium">
            <Palette className="size-4 text-muted" aria-hidden /> Couleur du nom et des titres de sections
          </legend>
          <div className="flex flex-wrap gap-2">
            {ACCENTS.map((a) => {
              const selected = cv.settings.accent.toLowerCase() === a.value.toLowerCase();
              return (
                <button
                  key={a.value}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => update((c) => ({ ...c, settings: { ...c.settings, accent: a.value } }))}
                  className={`flex items-center gap-2 rounded-full border px-2.5 py-1 text-sm ${selected ? "border-ink bg-surface font-medium" : "border-line hover:border-muted"}`}
                >
                  <span className="size-4 rounded-full" style={{ backgroundColor: a.value }} aria-hidden />
                  {a.label}
                </button>
              );
            })}
          </div>
          <p className="mt-1.5 text-xs text-muted">Seuls le nom et les titres changent de couleur : le texte reste noir, sans effet sur la lecture par les ATS.</p>
        </fieldset>
        {error && <Alert>{error}</Alert>}
        <div className="flex flex-wrap gap-3">
          <Button disabled={!!busy} onClick={() => exportAs("pdf")}>
            {busy === "pdf" ? <Spinner /> : <FileDown className="size-4" aria-hidden />} Télécharger en PDF
          </Button>
          <Button variant="secondary" disabled={!!busy} onClick={() => exportAs("docx")}>
            {busy === "docx" ? <Spinner /> : <FileText className="size-4" aria-hidden />} Télécharger en Word
          </Button>
          <Button variant="ghost" onClick={() => download(new Blob([JSON.stringify(cv, null, 2)], { type: "application/json" }), `CV-${name}.json`)}>
            <Download className="size-4" aria-hidden /> Enregistrer le projet (.json)
          </Button>
        </div>
        <p className="text-xs text-muted">Le fichier .json se rouvre depuis l&apos;écran de connexion pour retravailler le CV sans repasser par LinkedIn.</p>
      </section>

      <section className="rounded-lg border border-line bg-white p-5">
        <h2 className="text-sm font-medium">Ce que le format garantit</h2>
        <ul className="mt-2 space-y-1 text-sm text-muted">
          {CHECKS.map((c) => (
            <li key={c} className="flex gap-2"><span aria-hidden className="text-ok">✓</span>{c}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}
