"use client";

import { useState, useRef } from "react";
import { useCV } from "@/context/CVContext";
import { Linkedin, ArrowRight, Sparkles, FileText, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface WelcomeStepProps {
  onNext: () => void;
}

interface ScrapeProgress {
  step: string;
  percent: number;
}

interface MfaChallenge {
  requestId: string;
  message: string;
  timeoutSeconds: number;
}

export function WelcomeStep({ onNext }: WelcomeStepProps) {
  const { dispatch } = useCV();
  const [linkedinUrl, setLinkedinUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState<ScrapeProgress | null>(null);
  const [mfaChallenge, setMfaChallenge] = useState<MfaChallenge | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [submittingMfa, setSubmittingMfa] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  async function handleLinkedInImport() {
    if (!linkedinUrl.trim()) return;

    const urlPattern = /^https?:\/\/(www\.)?linkedin\.com\/in\/[\w%-]+\/?$/;
    if (!urlPattern.test(linkedinUrl.trim())) {
      setError("Veuillez entrer une URL LinkedIn valide (ex: https://linkedin.com/in/votre-profil)");
      return;
    }

    setLoading(true);
    setError("");
    setMfaChallenge(null);
    setMfaCode("");
    setProgress({ step: "Démarrage de l'import...", percent: 0 });

    // Abort previous request if any
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const url = `/api/linkedin/scrape?url=${encodeURIComponent(linkedinUrl.trim())}`;
      const res = await fetch(url, { signal: controller.signal });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "Erreur lors de l'import");
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("Streaming non supporté");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse SSE events from buffer
        const lines = buffer.split("\n");
        buffer = lines.pop() || ""; // Keep incomplete line

        let eventType = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            const jsonStr = line.slice(6);
            try {
              const data = JSON.parse(jsonStr);

              if (eventType === "progress") {
                setProgress({ step: data.step, percent: data.percent });
              } else if (eventType === "mfa_required") {
                setMfaChallenge({
                  requestId: data.requestId,
                  message: data.message || "Un code de vérification LinkedIn est requis.",
                  timeoutSeconds: data.timeoutSeconds || 300,
                });
                setProgress({ step: "Code LinkedIn requis: en attente...", percent: 16 });
              } else if (eventType === "complete") {
                dispatch({ type: "IMPORT_DATA", payload: data });
                setProgress({ step: "Import terminé ✓", percent: 100 });
                setMfaChallenge(null);
                setTimeout(() => onNext(), 800);
                return;
              } else if (eventType === "error") {
                throw new Error(data.error);
              }
            } catch (e) {
              if (e instanceof SyntaxError) continue;
              throw e;
            }
          }
        }
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      setError(err instanceof Error ? err.message : "Erreur lors de l'import LinkedIn");
      setProgress(null);
      setMfaChallenge(null);
    } finally {
      setLoading(false);
    }
  }

  function handleCancel() {
    abortRef.current?.abort();
    setLoading(false);
    setProgress(null);
    setMfaChallenge(null);
    setMfaCode("");
  }

  async function handleSubmitMfaCode() {
    if (!mfaChallenge || !mfaCode.trim()) return;
    setSubmittingMfa(true);
    setError("");

    try {
      const res = await fetch("/api/linkedin/scrape", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ requestId: mfaChallenge.requestId, code: mfaCode.trim() }),
      });

      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.error || "Impossible d'envoyer le code de vérification");
      }

      setProgress({ step: "Code envoyé, reprise du scraping...", percent: 17 });
      setMfaCode("");
      setMfaChallenge(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur lors de l'envoi du code");
    } finally {
      setSubmittingMfa(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto text-center space-y-10">
      <div className="space-y-4">
        <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-indigo-50 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 text-sm font-medium">
          <Sparkles className="w-4 h-4" />
          Générateur de CV ATS
        </div>
        <h1 className="text-4xl sm:text-5xl font-bold text-zinc-900 dark:text-white leading-tight">
          Créez votre CV
          <span className="block bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">
            parfaitement optimisé
          </span>
        </h1>
        <p className="text-lg text-zinc-500 dark:text-zinc-400 max-w-lg mx-auto">
          Répondez à quelques questions et obtenez un CV professionnel
          compatible avec tous les systèmes ATS.
        </p>
      </div>

      <div className="bg-white dark:bg-zinc-800/50 rounded-2xl border border-zinc-200 dark:border-zinc-700 p-6 space-y-4">
        <div className="flex items-center gap-3 text-left">
          <div className="w-10 h-10 rounded-xl bg-blue-100 dark:bg-blue-500/20 flex items-center justify-center">
            <Linkedin className="w-5 h-5 text-blue-600 dark:text-blue-400" />
          </div>
          <div>
            <h3 className="font-semibold text-zinc-900 dark:text-white">
              Importer depuis LinkedIn
            </h3>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              Vos informations seront extraites automatiquement
            </p>
          </div>
        </div>

        <div className="flex gap-2">
          <input
            type="url"
            value={linkedinUrl}
            onChange={(e) => {
              setLinkedinUrl(e.target.value);
              setError("");
            }}
            disabled={loading}
            placeholder="https://linkedin.com/in/votre-profil"
            className={cn(
              "flex-1 px-4 py-3 rounded-xl border bg-white dark:bg-zinc-900",
              "border-zinc-200 dark:border-zinc-700",
              "text-zinc-900 dark:text-zinc-100 placeholder-zinc-400",
              "focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500",
              "transition-all disabled:opacity-50"
            )}
          />
          {loading ? (
            <button
              onClick={handleCancel}
              className="px-5 py-3 rounded-xl font-medium transition-all bg-rose-600 hover:bg-rose-700 text-white flex items-center gap-2"
            >
              Annuler
            </button>
          ) : (
            <button
              onClick={handleLinkedInImport}
              disabled={!linkedinUrl.trim()}
              className={cn(
                "px-5 py-3 rounded-xl font-medium transition-all",
                "bg-blue-600 hover:bg-blue-700 text-white",
                "disabled:opacity-50 disabled:cursor-not-allowed",
                "flex items-center gap-2"
              )}
            >
              Importer
            </button>
          )}
        </div>

        {/* Progress bar */}
        {progress && (
          <div className="space-y-2 text-left">
            <div className="flex items-center gap-2">
              {progress.percent < 100 && (
                <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />
              )}
              <p className="text-sm text-zinc-600 dark:text-zinc-300 font-medium">
                {progress.step}
              </p>
            </div>
            <div className="w-full h-2.5 bg-zinc-100 dark:bg-zinc-700 rounded-full overflow-hidden">
              <div
                className={cn(
                  "h-full rounded-full transition-all duration-500 ease-out",
                  progress.percent >= 100
                    ? "bg-emerald-500"
                    : "bg-gradient-to-r from-blue-500 to-indigo-500"
                )}
                style={{ width: `${progress.percent}%` }}
              />
            </div>
            <p className="text-xs text-zinc-400 dark:text-zinc-500">
              {progress.percent}% — Ne fermez pas cette page
            </p>
          </div>
        )}

        {mfaChallenge && (
          <div className="rounded-xl border border-amber-300/60 bg-amber-50 dark:bg-amber-500/10 p-4 text-left space-y-3">
            <p className="text-sm font-semibold text-amber-900 dark:text-amber-200">
              Vérification LinkedIn requise
            </p>
            <p className="text-xs text-amber-800 dark:text-amber-300">
              {mfaChallenge.message}
            </p>
            <p className="text-xs text-amber-700 dark:text-amber-400">
              Le scraping est en pause. Saisissez le code reçu par e-mail (expiration dans {Math.floor(mfaChallenge.timeoutSeconds / 60)} min).
            </p>

            <div className="flex gap-2">
              <input
                type="text"
                inputMode="numeric"
                value={mfaCode}
                onChange={(e) => setMfaCode(e.target.value)}
                placeholder="Code de vérification"
                className={cn(
                  "flex-1 px-4 py-2.5 rounded-lg border bg-white dark:bg-zinc-900",
                  "border-amber-300/70 dark:border-amber-600/50",
                  "text-zinc-900 dark:text-zinc-100 placeholder-zinc-400",
                  "focus:outline-none focus:ring-2 focus:ring-amber-500/40 focus:border-amber-500",
                  "transition-all"
                )}
              />
              <button
                onClick={handleSubmitMfaCode}
                disabled={!mfaCode.trim() || submittingMfa}
                className={cn(
                  "px-4 py-2.5 rounded-lg font-medium transition-all",
                  "bg-amber-600 hover:bg-amber-700 text-white",
                  "disabled:opacity-50 disabled:cursor-not-allowed"
                )}
              >
                {submittingMfa ? "Envoi..." : "Valider"}
              </button>
            </div>
          </div>
        )}

        {error && (
          <p className="text-sm text-rose-500 text-left">{error}</p>
        )}
      </div>

      <div className="relative flex items-center gap-4">
        <div className="flex-1 h-px bg-zinc-200 dark:bg-zinc-700" />
        <span className="text-sm text-zinc-400 dark:text-zinc-500 font-medium">ou</span>
        <div className="flex-1 h-px bg-zinc-200 dark:bg-zinc-700" />
      </div>

      <button
        onClick={onNext}
        disabled={loading}
        className={cn(
          "inline-flex items-center gap-3 px-8 py-4 rounded-2xl font-semibold text-lg",
          "bg-gradient-to-r from-indigo-600 to-purple-600 text-white",
          "hover:from-indigo-700 hover:to-purple-700",
          "shadow-lg shadow-indigo-500/25 hover:shadow-xl hover:shadow-indigo-500/30",
          "transition-all duration-300 hover:-translate-y-0.5",
          "disabled:opacity-50 disabled:cursor-not-allowed"
        )}
      >
        <FileText className="w-5 h-5" />
        Commencer depuis zéro
        <ArrowRight className="w-5 h-5" />
      </button>
    </div>
  );
}
