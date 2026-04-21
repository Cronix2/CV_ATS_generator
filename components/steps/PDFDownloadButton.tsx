"use client";

import { PDFDownloadLink } from "@react-pdf/renderer";
import { CVDocument } from "@/components/pdf/CVDocument";
import { Download } from "lucide-react";
import type { CVData } from "@/lib/types";
import { cn } from "@/lib/utils";

export function PDFDownloadButton({ cvData }: { cvData: CVData }) {
  const fileName = `CV_${cvData.personalInfo.firstName}_${cvData.personalInfo.lastName}`.replace(/\s+/g, "_") || "CV_ATS";

  return (
    <PDFDownloadLink
      document={<CVDocument data={cvData} />}
      fileName={`${fileName}.pdf`}
    >
      {({ loading }) => (
        <button
          disabled={loading}
          className={cn(
            "px-6 py-3 rounded-xl font-semibold transition-all flex items-center gap-2",
            "bg-gradient-to-r from-indigo-600 to-purple-600 text-white",
            "hover:from-indigo-700 hover:to-purple-700",
            "shadow-lg shadow-indigo-500/25",
            "disabled:opacity-50 disabled:cursor-wait"
          )}
        >
          <Download className="w-5 h-5" />
          {loading ? "Génération..." : "Télécharger le PDF"}
        </button>
      )}
    </PDFDownloadLink>
  );
}
