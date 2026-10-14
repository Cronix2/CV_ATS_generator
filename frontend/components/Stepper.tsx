"use client";

import { Download, KeyRound, ListChecks, ScanSearch, Sparkles, Undo2, type LucideIcon } from "lucide-react";
import { hasContent, useStore, type Step } from "@/lib/store";
import { Logo } from "./Logo";

const STEPS: { id: Step; label: string; Icon: LucideIcon }[] = [
  { id: "connect", label: "Connexion", Icon: KeyRound },
  { id: "scrape", label: "Extraction", Icon: ScanSearch },
  { id: "edit", label: "Tri et édition", Icon: ListChecks },
  { id: "ai", label: "Agent IA", Icon: Sparkles },
  { id: "export", label: "Export", Icon: Download },
];

export function Stepper() {
  const { step, setStep, cv, jobId, lastCheckpoint, undo } = useStore();
  const current = STEPS.findIndex((s) => s.id === step);
  const reachable = (id: Step) => id === "connect" || (id === "scrape" ? Boolean(jobId) : hasContent(cv));

  return (
    <header className="sticky top-0 z-20 border-b border-line bg-white/95 backdrop-blur">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2.5 lg:px-8">
        <button type="button" onClick={() => setStep("connect")} aria-label="PasseFiltre, retour à l'accueil" className="rounded-md">
          <Logo />
        </button>
        <nav aria-label="Étapes" className="-mx-1 overflow-x-auto">
          <ol className="flex gap-1">
            {STEPS.map((s, i) => {
              const active = s.id === step;
              const done = i < current;
              const isAi = s.id === "ai";
              return (
                <li key={s.id}>
                  <button
                    type="button"
                    disabled={!reachable(s.id) || active}
                    onClick={() => setStep(s.id)}
                    aria-current={active ? "step" : undefined}
                    className={`flex items-center gap-2 whitespace-nowrap rounded-md px-2.5 py-1.5 text-sm transition-colors ${
                      active
                        ? isAi ? "bg-ai-soft font-medium text-ai" : "bg-brand-soft font-medium text-brand"
                        : "text-muted enabled:hover:bg-ink/5 enabled:hover:text-ink disabled:opacity-45"
                    }`}
                  >
                    <s.Icon className={`size-4 ${done ? "text-ok" : ""}`} aria-hidden />
                    {s.label}
                  </button>
                </li>
              );
            })}
          </ol>
        </nav>
        {lastCheckpoint && (
          <button
            type="button"
            onClick={undo}
            title={`Annuler : ${lastCheckpoint}`}
            className="ml-auto flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1.5 text-sm text-ink hover:border-brand hover:text-brand"
          >
            <Undo2 className="size-4" aria-hidden />
            <span className="max-w-56 truncate">Annuler : {lastCheckpoint}</span>
          </button>
        )}
      </div>
    </header>
  );
}
