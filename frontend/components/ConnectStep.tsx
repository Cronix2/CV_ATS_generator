"use client";

import { ScanSearch, Sparkles } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { hasContent, normalizeCV, useStore } from "@/lib/store";
import { emptyCV } from "@/lib/types";
import { Alert, Button, Field, IconTile, Input, Spinner } from "./ui";

// Prefills URL + model; the key is always typed by the user.
const PROVIDERS = [
  { label: "OpenAI", base_url: "", model: "gpt-4o-mini" },
  { label: "Paradigm (Orange LiveIntelligence)", base_url: "https://trust.liveintelligence.orange-business.com/api/v2", model: "alfred-4.2" },
  // Anthropic's OpenAI-compatible endpoint: no extra dependency, same agent/tool flow as the others.
  { label: "Anthropic (Claude)", base_url: "https://api.anthropic.com/v1", model: "claude-sonnet-5-5" },
  { label: "Mistral", base_url: "https://api.mistral.ai/v1", model: "mistral-small-latest" },
  { label: "OpenRouter", base_url: "https://openrouter.ai/api/v1", model: "openai/gpt-4o-mini" },
  { label: "Ollama (local, nécessite ALLOW_LOCAL_LLM=1 dans .env)", base_url: "http://localhost:11434/v1", model: "llama3.1" },
];

export function ConnectStep() {
  const { cv, update, llm, setLlm, setStep, setJobId, server, token, setToken } = useStore();
  const serverKey = Boolean(server?.llm.server_key);
  const [url, setUrl] = useState(cv.profile.basics.linkedin_url);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showBrowser, setShowBrowser] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [llmStatus, setLlmStatus] = useState<{ tone: "ok" | "danger"; text: string } | null>(null);
  const [testing, setTesting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const job = await api.startScrape({ profile_url: url, email, password, show_browser: showBrowser });
      setPassword("");
      setJobId(job.id);
      setStep("scrape");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const [sessionNote, setSessionNote] = useState("");

  // Deletes the LinkedIn cookies kept for this account on the server (needs the same email + password).
  async function forgetSession() {
    setError("");
    setSessionNote("");
    try {
      const { removed } = await api.forgetLinkedInSession({ email, password });
      setSessionNote(removed ? "Session LinkedIn effacée du serveur." : "Aucune session enregistrée pour ces identifiants.");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function testLlm() {
    setTesting(true);
    setLlmStatus(null);
    try {
      await api.testLLM(llm);
      setLlmStatus({ tone: "ok", text: `Connexion réussie avec ${llm.model}.` });
    } catch (err) {
      setLlmStatus({ tone: "danger", text: (err as Error).message });
    } finally {
      setTesting(false);
    }
  }

  const confirmReplace = () => !hasContent(cv) || confirm("Remplacer le CV en cours ?");

  async function importJson(file: File) {
    if (!confirmReplace()) return;
    try {
      const next = normalizeCV(JSON.parse(await file.text()));
      update(() => next);
      setStep("edit");
    } catch {
      setError("Ce fichier n'est pas un CV enregistré valide (.json).");
    }
  }

  return (
    <div className="space-y-10">
      <section>
        <h1 className="text-3xl font-semibold tracking-tight text-balance">
          Transformez un profil LinkedIn en CV qu&apos;un ATS sait lire.
        </h1>
        <p className="mt-3 max-w-[62ch] text-muted">
          L&apos;outil lit le profil, vous choisissez ce qui reste et vous corrigez ce qui doit l&apos;être, puis vous
          téléchargez un CV en une colonne, en texte réel, avec des intitulés de sections standards.
        </p>
      </section>

      <form onSubmit={submit} className="space-y-4 rounded-lg border border-line border-t-3 border-t-brand bg-white p-5 sm:p-6">
        <div className="flex items-center gap-3">
          <IconTile Icon={ScanSearch} color="#2557d6" />
          <h2 className="text-lg font-semibold">Profil à extraire</h2>
        </div>
        {server?.auth_required && (
          <Field label="Jeton d'accès PasseFiltre" hint="Ce serveur est protégé : demandez le jeton (PASSEFILTRE_TOKEN) à la personne qui l'héberge. Il reste mémorisé sur cet appareil ; videz le champ pour l'oublier.">
            <Input type="password" required autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} />
          </Field>
        )}
        <Field label="Adresse du profil LinkedIn">
          <Input type="url" required value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://www.linkedin.com/in/votre-identifiant/" />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Email du compte LinkedIn">
            <Input type="email" required autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="Mot de passe LinkedIn">
            <Input type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
        </div>
        {/* In Docker there is no screen to show a browser window on. */}
        {!server?.docker && (
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-0.5 accent-brand" checked={showBrowser} onChange={(e) => setShowBrowser(e.target.checked)} />
            <span>
              Afficher le navigateur pendant l&apos;extraction
              <span className="block text-xs text-muted">À cocher si LinkedIn demande un captcha : vous le résolvez dans la fenêtre.</span>
            </span>
          </label>
        )}
        <p className="text-xs text-muted">
          Le compte sert à ouvrir une session LinkedIn sur votre machine pour lire le profil, à un rythme raisonnable.
          Le mot de passe n&apos;est ni enregistré ni journalisé ; seuls les cookies de session sont gardés localement
          (dossier <code>backend/.sessions</code>) pour éviter de se reconnecter à chaque fois.
          {server?.remote_captcha && " Si LinkedIn affiche un CAPTCHA, vous le résoudrez vous-même depuis cette page."}
        </p>
        {error && <Alert>{error}</Alert>}
        <div className="flex flex-wrap items-center gap-3 pt-1">
          <Button type="submit" disabled={busy}>
            {busy && <Spinner />} Extraire le profil
          </Button>
          {hasContent(cv) && (
            <Button variant="secondary" onClick={() => setStep("edit")}>
              Reprendre le CV en cours
            </Button>
          )}
          <Button variant="ghost" className="ml-auto" disabled={!email || !password || busy} onClick={forgetSession}>
            Oublier ma session LinkedIn
          </Button>
        </div>
        {sessionNote && <Alert tone="info">{sessionNote}</Alert>}
      </form>

      <section className="space-y-4 rounded-lg border border-line border-t-3 border-t-ai bg-white p-5 sm:p-6">
        <div className="flex items-start gap-3">
          <IconTile Icon={Sparkles} color="#6d3fd9" />
          <div>
            <h2 className="text-lg font-semibold">Agent IA (facultatif)</h2>
            <p className="mt-1 text-sm text-muted">
              Avec une clé d&apos;API compatible OpenAI (OpenAI, Mistral, Groq, OpenRouter, Ollama…), un agent recherche
              sur le web ce qu&apos;attend le poste visé et améliore le CV directement. Chaque modification reste annulable.
            </p>
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Fournisseur" className="sm:col-span-2">
            <select
              className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm focus:border-ink focus:outline-none"
              value={PROVIDERS.findIndex((p) => p.base_url === llm.base_url && p.model === llm.model)}
              onChange={(e) => {
                const p = PROVIDERS[Number(e.target.value)];
                if (p) setLlm({ ...llm, base_url: p.base_url, model: p.model });
              }}
            >
              <option value={-1}>Autre (saisie manuelle)</option>
              {PROVIDERS.map((p, i) => <option key={p.label} value={i}>{p.label}</option>)}
            </select>
          </Field>
          <Field label="Clé d'API">
            <Input type="password" autoComplete="off" value={llm.api_key} onChange={(e) => setLlm({ ...llm, api_key: e.target.value })} placeholder="sk-…" />
          </Field>
          <Field label="Modèle">
            <Input value={llm.model} onChange={(e) => setLlm({ ...llm, model: e.target.value })} placeholder="gpt-4o-mini" />
          </Field>
          <Field label="URL de l'API" hint="Laissez vide pour OpenAI. Sinon, l'adresse qui précède /chat/completions dans la doc du fournisseur." className="sm:col-span-2">
            <Input type="url" value={llm.base_url} onChange={(e) => setLlm({ ...llm, base_url: e.target.value })} placeholder="https://api.mistral.ai/v1" />
          </Field>
        </div>
        {serverKey && !llm.api_key && (
          <Alert tone="ai">
            Un LLM est déjà configuré sur le serveur (fichier <code>.env</code>, modèle <strong>{server?.llm.model}</strong>) :
            laissez la clé vide pour l&apos;utiliser.
          </Alert>
        )}
        <p className="text-xs text-muted">La clé saisie ici reste dans cet onglet et disparaît à sa fermeture.</p>
        {llmStatus && <Alert tone={llmStatus.tone}>{llmStatus.text}</Alert>}
        <Button variant="secondary" disabled={(!llm.api_key && !serverKey) || testing} onClick={testLlm}>
          {testing && <Spinner />} Tester la connexion
        </Button>
      </section>

      <section className="flex flex-wrap items-center gap-3 text-sm text-muted">
        <span>Sans LinkedIn :</span>
        <Button variant="secondary" onClick={() => fileRef.current?.click()}>
          Ouvrir un CV enregistré (.json)
        </Button>
        <Button variant="ghost" onClick={() => { if (confirmReplace()) { update(() => emptyCV()); setStep("edit"); } }}>
          Partir d&apos;un CV vide
        </Button>
        <input ref={fileRef} type="file" accept="application/json,.json" hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) importJson(f); }} />
      </section>
    </div>
  );
}
