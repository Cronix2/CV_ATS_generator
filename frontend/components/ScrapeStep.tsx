"use client";

import { useEffect, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { normalizeCV, useStore } from "@/lib/store";
import type { Job } from "@/lib/types";
import { Alert, Button, Field, Input, Spinner } from "./ui";

export function ScrapeStep() {
  const { jobId, setJobId, update, setStep } = useStore();
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [code, setCode] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (!jobId) return;
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const j = await api.job(jobId);
        if (stop) return;
        setJob(j);
        if (j.status === "done" && j.result) {
          update((cv) => ({ ...normalizeCV(j.result), settings: cv.settings }));
          setJobId(""); // apply the result once: coming back here must not overwrite later edits
          setStep("edit");
          return;
        }
        if (j.status !== "error") timer = setTimeout(poll, 1500);
      } catch (err) {
        if (!stop) setError((err as Error).message);
      }
    };
    poll();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [jobId, setJobId, update, setStep]);

  async function sendCode(e: FormEvent) {
    e.preventDefault();
    setSending(true);
    try {
      await api.sendCode(jobId, code);
      setCode("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSending(false);
    }
  }

  const failed = job?.status === "error" || Boolean(error);
  const last = job?.messages.at(-1) ?? "Démarrage du navigateur…";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Lecture du profil LinkedIn</h1>
        <p className="mt-2 text-muted">Comptez une à deux minutes : chaque section est ouverte l&apos;une après l&apos;autre, sans précipitation.</p>
      </div>

      <div className="rounded-lg border border-line bg-white p-5 sm:p-6">
        <div className="flex items-center gap-3 text-sm font-medium" aria-live="polite">
          {!failed && <Spinner />}
          {failed ? "L'extraction s'est arrêtée." : last}
        </div>
        <div className="mt-4 h-2 overflow-hidden rounded-full bg-desk" role="progressbar" aria-valuenow={job?.percent ?? 0} aria-valuemin={0} aria-valuemax={100}>
          <div className="h-full bg-mark transition-[width] duration-500" style={{ width: `${Math.max(job?.percent ?? 0, 3)}%` }} />
        </div>

        {job?.status === "needs_code" && (
          <form onSubmit={sendCode} className="mt-6 space-y-3 rounded-md border border-mark bg-mark/15 p-4">
            <p className="text-sm font-medium">{job.prompt}</p>
            <Field label="Code de vérification">
              <Input autoFocus inputMode="numeric" autoComplete="one-time-code" required value={code} onChange={(e) => setCode(e.target.value)} className="max-w-48" />
            </Field>
            <Button type="submit" disabled={sending}>
              {sending && <Spinner />} Envoyer le code
            </Button>
          </form>
        )}

        {job && job.messages.length > (failed ? 0 : 1) && (
          <ol className="mt-6 space-y-1 border-t border-line pt-4 text-sm text-muted">
            {(failed ? job.messages : job.messages.slice(0, -1)).map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ol>
        )}
      </div>

      {failed && (
        <div className="space-y-3">
          <Alert>{job?.error || error}</Alert>
          <Button variant="secondary" onClick={() => setStep("connect")}>
            Modifier les informations de connexion
          </Button>
        </div>
      )}
    </div>
  );
}
