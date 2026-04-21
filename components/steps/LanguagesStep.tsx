"use client";

import { useCV } from "@/context/CVContext";
import { AutocompleteInput } from "@/components/AutocompleteInput";
import { LANGUAGES_LIST, LANGUAGE_LEVELS } from "@/lib/suggestions";
import { generateId, cn } from "@/lib/utils";
import { Plus, Trash2, Globe } from "lucide-react";
import type { Language } from "@/lib/types";

export function LanguagesStep() {
  const { cvData, dispatch } = useCV();
  const items = cvData.languages;

  function addItem() {
    const newItem: Language = {
      id: generateId(),
      language: "",
      level: "",
    };
    dispatch({ type: "SET_LANGUAGES", payload: [...items, newItem] });
  }

  function updateItem(id: string, updates: Partial<Language>) {
    dispatch({
      type: "SET_LANGUAGES",
      payload: items.map((item) => (item.id === id ? { ...item, ...updates } : item)),
    });
  }

  function removeItem(id: string) {
    dispatch({
      type: "SET_LANGUAGES",
      payload: items.filter((item) => item.id !== id),
    });
  }

  return (
    <div className="space-y-6 max-w-2xl mx-auto">
      <div>
        <h2 className="text-2xl font-bold text-zinc-900 dark:text-white">Langues</h2>
        <p className="text-zinc-500 dark:text-zinc-400 mt-1">
          Indiquez les langues que vous maîtrisez et votre niveau.
        </p>
      </div>

      {items.length === 0 && (
        <div className="text-center py-12 border-2 border-dashed border-zinc-200 dark:border-zinc-700 rounded-2xl">
          <Globe className="w-12 h-12 mx-auto text-zinc-300 dark:text-zinc-600 mb-3" />
          <p className="text-zinc-500 dark:text-zinc-400 mb-4">
            Aucune langue ajoutée
          </p>
          <button
            onClick={addItem}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
          >
            <Plus className="w-4 h-4" /> Ajouter une langue
          </button>
        </div>
      )}

      {items.map((item, index) => (
        <div
          key={item.id}
          className="p-5 bg-white dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700 rounded-2xl"
        >
          <div className="flex items-start gap-4">
            <div className="flex-1 grid grid-cols-1 sm:grid-cols-2 gap-4">
              <AutocompleteInput
                label={`Langue ${index + 1}`}
                value={item.language}
                onChange={(v) => updateItem(item.id, { language: v })}
                suggestions={LANGUAGES_LIST}
                placeholder="Français, Anglais..."
                required
              />
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">
                  Niveau
                </label>
                <select
                  value={item.level}
                  onChange={(e) => updateItem(item.id, { level: e.target.value })}
                  className={cn(
                    "w-full px-4 py-3 rounded-xl border bg-white dark:bg-zinc-900",
                    "border-zinc-200 dark:border-zinc-700 text-zinc-900 dark:text-zinc-100",
                    "focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500 transition-all"
                  )}
                >
                  <option value="">Sélectionner un niveau</option>
                  {LANGUAGE_LEVELS.map((level) => (
                    <option key={level} value={level}>
                      {level}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <button
              onClick={() => removeItem(item.id)}
              className="mt-7 p-2 text-zinc-400 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-500/10 rounded-lg transition-colors"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>
      ))}

      {items.length > 0 && (
        <button
          onClick={addItem}
          className="w-full py-3 border-2 border-dashed border-zinc-300 dark:border-zinc-600 rounded-2xl text-zinc-500 dark:text-zinc-400 hover:border-indigo-400 hover:text-indigo-600 dark:hover:border-indigo-500 dark:hover:text-indigo-400 transition-colors flex items-center justify-center gap-2"
        >
          <Plus className="w-4 h-4" /> Ajouter une autre langue
        </button>
      )}
    </div>
  );
}
