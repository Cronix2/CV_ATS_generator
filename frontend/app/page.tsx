"use client";

import { useEffect } from "react";
import { AIStep } from "@/components/AIStep";
import { ConnectStep } from "@/components/ConnectStep";
import { EditStep } from "@/components/EditStep";
import { ExportStep } from "@/components/ExportStep";
import { Preview } from "@/components/Preview";
import { ScrapeStep } from "@/components/ScrapeStep";
import { Stepper } from "@/components/Stepper";
import { StoreProvider, useStore } from "@/lib/store";

function Workbench() {
  const { step } = useStore();
  useEffect(() => window.scrollTo({ top: 0 }), [step]); // each step starts at its top
  const withPreview = step === "edit" || step === "ai" || step === "export";

  return (
    <>
      <Stepper />
      {withPreview ? (
        <main className="mx-auto grid max-w-[1400px] gap-6 px-4 pb-16 pt-6 lg:grid-cols-[minmax(0,1fr)_minmax(420px,560px)] lg:px-8">
          <div className="min-w-0">
            {step === "edit" && <EditStep />}
            {/* Kept mounted: a running agent keeps going while you edit or export. */}
            <div hidden={step !== "ai"}><AIStep /></div>
            {step === "export" && <ExportStep />}
          </div>
          <Preview />
        </main>
      ) : (
        <main className="mx-auto max-w-3xl px-4 pb-16 pt-10">
          {step === "connect" && <ConnectStep />}
          {step === "scrape" && <ScrapeStep />}
        </main>
      )}
    </>
  );
}

export default function Page() {
  return (
    <StoreProvider>
      <Workbench />
    </StoreProvider>
  );
}
