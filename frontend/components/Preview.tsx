"use client";

import { ChevronDown, CircleCheck, CircleX, Gauge } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { qualityChecks } from "@/lib/ats";
import { useStore } from "@/lib/store";
import { Spinner } from "./ui";

function QualityPanel() {
  const { cv } = useStore();
  const { score, checks } = qualityChecks(cv);
  const color = score >= 80 ? "var(--color-ok)" : score >= 50 ? "var(--color-warn)" : "var(--color-danger)";
  const todo = checks.filter((c) => !c.ok);

  return (
    <details className="group border-b border-line bg-white">
      <summary className="flex cursor-pointer list-none items-center gap-3 px-3 py-2.5 [&::-webkit-details-marker]:hidden">
        <Gauge className="size-4 text-muted" aria-hidden />
        <span className="text-sm font-medium">Qualité du CV</span>
        <span className="h-2 flex-1 overflow-hidden rounded-full bg-desk" role="meter" aria-valuenow={score} aria-valuemin={0} aria-valuemax={100} aria-label="Score de qualité">
          <span className="block h-full rounded-full transition-[width] duration-500" style={{ width: `${score}%`, backgroundColor: color }} />
        </span>
        <span className="w-12 text-right text-sm font-semibold tabular-nums" style={{ color }}>{score}%</span>
        <ChevronDown className="size-4 text-muted transition-transform group-open:rotate-180" aria-hidden />
      </summary>
      <ul className="max-h-60 space-y-1.5 overflow-y-auto px-3 pb-3 text-sm">
        {[...todo, ...checks.filter((c) => c.ok)].map((c) => (
          <li key={c.label} className="flex items-start gap-2">
            {c.ok ? <CircleCheck className="mt-0.5 size-4 shrink-0 text-ok" aria-hidden /> : <CircleX className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden />}
            <span>
              <span className={c.ok ? "text-muted" : "font-medium"}>{c.label}</span>
              {!c.ok && <span className="block text-xs text-muted">{c.hint}</span>}
            </span>
          </li>
        ))}
      </ul>
    </details>
  );
}

/** Shows the real PDF produced by the backend, so what you see is exactly what the ATS gets. */
export function Preview() {
  const { cv } = useStore();
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  // The target job does not change the PDF: typing an offer must not regenerate it.
  const { target: _target, ...printed } = cv.settings;
  const pdfKey = JSON.stringify([cv.profile, printed]);

  useEffect(() => {
    let cancelled = false;
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const { blob } = await api.exportFile(cv, "pdf");
        if (cancelled) return;
        setUrl((old) => {
          if (old) URL.revokeObjectURL(old);
          return URL.createObjectURL(blob);
        });
        setError("");
      } catch (err) {
        if (!cancelled) setError((err as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 700);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pdfKey]);

  return (
    <aside aria-label="Aperçu du CV" className="lg:sticky lg:top-20 lg:h-[calc(100dvh-6rem)]">
      <div className="flex h-full min-h-[70vh] flex-col overflow-hidden rounded-lg border border-line bg-[#d5dce3]">
        <QualityPanel />
        <div className="flex items-center justify-between px-3 py-2 text-xs text-muted">
          <span>Aperçu du PDF exporté</span>
          {loading && <Spinner />}
        </div>
        {error ? (
          <p className="m-3 rounded-md bg-white p-3 text-sm text-danger">{error}</p>
        ) : url ? (
          <iframe title="Aperçu du CV" src={`${url}#toolbar=0&navpanes=0&view=FitH`} className="w-full flex-1 bg-white" />
        ) : (
          <div className="grid flex-1 place-items-center text-sm text-muted">Génération de l&apos;aperçu…</div>
        )}
      </div>
    </aside>
  );
}
