"use client";

import { useCV } from "@/context/CVContext";
import { AutocompleteInput } from "@/components/AutocompleteInput";
import { CERTIFICATIONS_LIST, CERTIFICATION_ISSUERS } from "@/lib/suggestions";
import { generateId, cn } from "@/lib/utils";
import { Plus, Trash2, Award } from "lucide-react";
import type { Certification } from "@/lib/types";

export function CertificationsStep() {
  const { cvData, dispatch } = useCV();
  const items = cvData.certifications;

  function addItem() {
    const newItem: Certification = {
      id: generateId(),
      name: "",
      issuer: "",
      date: "",
      url: "",
    };
    dispatch({ type: "SET_CERTIFICATIONS", payload: [...items, newItem] });
  }

  function updateItem(id: string, updates: Partial<Certification>) {
    dispatch({
      type: "SET_CERTIFICATIONS",
      payload: items.map((item) => (item.id === id ? { ...item, ...updates } : item)),
    });
  }

  function removeItem(id: string) {
    dispatch({
      type: "SET_CERTIFICATIONS",
      payload: items.filter((item) => item.id !== id),
    });
  }

  return (
    <div className="space-y-6 max-w-2xl mx-auto">
      <div>
        <h2 className="text-2xl font-bold text-zinc-900 dark:text-white">
          Certifications & Diplômes
        </h2>
        <p className="text-zinc-500 dark:text-zinc-400 mt-1">
          Ajoutez vos certifications professionnelles et diplômes complémentaires.
        </p>
      </div>

      {items.length === 0 && (
        <div className="text-center py-12 border-2 border-dashed border-zinc-200 dark:border-zinc-700 rounded-2xl">
          <Award className="w-12 h-12 mx-auto text-zinc-300 dark:text-zinc-600 mb-3" />
          <p className="text-zinc-500 dark:text-zinc-400 mb-4">
            Aucune certification ajoutée
          </p>
          <button
            onClick={addItem}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
          >
            <Plus className="w-4 h-4" /> Ajouter une certification
          </button>
        </div>
      )}

      {items.map((item, index) => (
        <div
          key={item.id}
          className="p-5 bg-white dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700 rounded-2xl space-y-4"
        >
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-zinc-900 dark:text-white">
              Certification {index + 1}
            </h3>
            <button
              onClick={() => removeItem(item.id)}
              className="p-2 text-zinc-400 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-500/10 rounded-lg transition-colors"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>

          <AutocompleteInput
            label="Nom de la certification"
            value={item.name}
            onChange={(v) => updateItem(item.id, { name: v })}
            suggestions={CERTIFICATIONS_LIST}
            placeholder="AWS Certified Solutions Architect, TOEIC..."
            required
          />

          <AutocompleteInput
            label="Organisme délivrant"
            value={item.issuer}
            onChange={(v) => updateItem(item.id, { issuer: v })}
            suggestions={CERTIFICATION_ISSUERS}
            placeholder="Amazon Web Services, Google..."
          />

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">
                Date d&apos;obtention
              </label>
              <input
                type="month"
                value={item.date}
                onChange={(e) => updateItem(item.id, { date: e.target.value })}
                className={cn(
                  "w-full px-4 py-3 rounded-xl border bg-white dark:bg-zinc-900",
                  "border-zinc-200 dark:border-zinc-700 text-zinc-900 dark:text-zinc-100",
                  "focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500 transition-all"
                )}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">
                URL de vérification
              </label>
              <input
                type="url"
                value={item.url}
                onChange={(e) => updateItem(item.id, { url: e.target.value })}
                placeholder="https://..."
                className={cn(
                  "w-full px-4 py-3 rounded-xl border bg-white dark:bg-zinc-900",
                  "border-zinc-200 dark:border-zinc-700 text-zinc-900 dark:text-zinc-100",
                  "placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/40",
                  "focus:border-indigo-500 transition-all"
                )}
              />
            </div>
          </div>
        </div>
      ))}

      {items.length > 0 && (
        <button
          onClick={addItem}
          className="w-full py-3 border-2 border-dashed border-zinc-300 dark:border-zinc-600 rounded-2xl text-zinc-500 dark:text-zinc-400 hover:border-indigo-400 hover:text-indigo-600 dark:hover:border-indigo-500 dark:hover:text-indigo-400 transition-colors flex items-center justify-center gap-2"
        >
          <Plus className="w-4 h-4" /> Ajouter une autre certification
        </button>
      )}
    </div>
  );
}
