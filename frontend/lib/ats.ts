"use client";
import { useEffect, useState } from "react";
import { api } from "./api";
import type { CV } from "./types";

export interface ATSAnalysis {
  keywords: string[]; found: string[]; missing: string[]; percent: number | null;
  score: number; checks: { label: string; ok: boolean; hint: string }[];
  suggested_keywords: string[];
}

/** The backend owns the heuristics. Never display a result for an older CV. */
export function useATS(cv: CV) {
  const key = JSON.stringify(cv);
  const [state, setState] = useState<{ key: string; data?: ATSAnalysis; error?: string }>({ key: "" });
  useEffect(() => {
    let obsolete = false;
    const timer = setTimeout(() => {
      api.ats(cv).then(data => { if (!obsolete) setState({ key, data }); })
        .catch(() => { if (!obsolete) setState({ key, error: "Analyse ATS indisponible." }); });
    }, 300);
    return () => { obsolete = true; clearTimeout(timer); };
    // The serialized value, rather than object identity, defines a new analysis.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return state.key === key ? state : { key };
}
