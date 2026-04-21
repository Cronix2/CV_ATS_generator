"use client";

import { useCV } from "@/context/CVContext";
import { AutocompleteInput } from "@/components/AutocompleteInput";
import { COMPANIES, JOB_TITLES, CITIES } from "@/lib/suggestions";
import { generateId, cn } from "@/lib/utils";
import { Plus, Trash2, Briefcase } from "lucide-react";
import type { Experience } from "@/lib/types";

export function ExperienceStep() {
  const { cvData, dispatch } = useCV();
  const items = cvData.experience;

  function addItem() {
    const newItem: Experience = {
      id: generateId(),
      company: "",
      title: "",
      startDate: "",
      endDate: "",
      current: false,
      description: "",
      location: "",
    };
    dispatch({ type: "SET_EXPERIENCE", payload: [...items, newItem] });
  }

  function updateItem(id: string, updates: Partial<Experience>) {
    dispatch({
      type: "SET_EXPERIENCE",
      payload: items.map((item) => (item.id === id ? { ...item, ...updates } : item)),
    });
  }

  function removeItem(id: string) {
    dispatch({
      type: "SET_EXPERIENCE",
      payload: items.filter((item) => item.id !== id),
    });
  }

  return (
    <div className="space-y-6 max-w-2xl mx-auto">
      <div>
        <h2 className="text-2xl font-bold text-zinc-900 dark:text-white">
          Expérience professionnelle
        </h2>
        <p className="text-zinc-500 dark:text-zinc-400 mt-1">
          Ajoutez vos expériences, du poste le plus récent au plus ancien.
        </p>
      </div>

      {items.length === 0 && (
        <div className="text-center py-12 border-2 border-dashed border-zinc-200 dark:border-zinc-700 rounded-2xl">
          <Briefcase className="w-12 h-12 mx-auto text-zinc-300 dark:text-zinc-600 mb-3" />
          <p className="text-zinc-500 dark:text-zinc-400 mb-4">
            Aucune expérience ajoutée
          </p>
          <button
            onClick={addItem}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
          >
            <Plus className="w-4 h-4" /> Ajouter une expérience
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
              Expérience {index + 1}
            </h3>
            <button
              onClick={() => removeItem(item.id)}
              className="p-2 text-zinc-400 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-500/10 rounded-lg transition-colors"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>

          <AutocompleteInput
            label="Entreprise"
            value={item.company}
            onChange={(v) => updateItem(item.id, { company: v })}
            suggestions={COMPANIES}
            placeholder="Commencez à taper le nom de l'entreprise..."
            required
          />

          <AutocompleteInput
            label="Poste"
            value={item.title}
            onChange={(v) => updateItem(item.id, { title: v })}
            suggestions={JOB_TITLES}
            placeholder="Développeur Full Stack, Chef de Projet..."
            required
          />

          <AutocompleteInput
            label="Lieu"
            value={item.location}
            onChange={(v) => updateItem(item.id, { location: v })}
            suggestions={CITIES}
            placeholder="Paris, Remote..."
          />

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">
                Date de début
              </label>
              <input
                type="month"
                value={item.startDate}
                onChange={(e) => updateItem(item.id, { startDate: e.target.value })}
                className={cn(
                  "w-full px-4 py-3 rounded-xl border bg-white dark:bg-zinc-900",
                  "border-zinc-200 dark:border-zinc-700 text-zinc-900 dark:text-zinc-100",
                  "focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500 transition-all"
                )}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">
                Date de fin
              </label>
              <input
                type="month"
                value={item.endDate}
                onChange={(e) => updateItem(item.id, { endDate: e.target.value })}
                disabled={item.current}
                className={cn(
                  "w-full px-4 py-3 rounded-xl border bg-white dark:bg-zinc-900",
                  "border-zinc-200 dark:border-zinc-700 text-zinc-900 dark:text-zinc-100",
                  "focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500 transition-all",
                  item.current && "opacity-50"
                )}
              />
              <label className="flex items-center gap-2 mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                <input
                  type="checkbox"
                  checked={item.current}
                  onChange={(e) => updateItem(item.id, { current: e.target.checked, endDate: "" })}
                  className="rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500"
                />
                Poste actuel
              </label>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">
              Description des missions
            </label>
            <textarea
              value={item.description}
              onChange={(e) => updateItem(item.id, { description: e.target.value })}
              rows={4}
              placeholder={"• Développement de fonctionnalités front-end avec React\n• Mise en place de pipelines CI/CD\n• Collaboration avec l'équipe produit..."}
              className={cn(
                "w-full px-4 py-3 rounded-xl border bg-white dark:bg-zinc-900",
                "border-zinc-200 dark:border-zinc-700 text-zinc-900 dark:text-zinc-100",
                "placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/40",
                "focus:border-indigo-500 transition-all resize-none"
              )}
            />
            <p className="text-xs text-zinc-400 mt-1">
              Astuce : commencez chaque point par un verbe d&apos;action et quantifiez vos résultats.
            </p>
          </div>
        </div>
      ))}

      {items.length > 0 && (
        <button
          onClick={addItem}
          className="w-full py-3 border-2 border-dashed border-zinc-300 dark:border-zinc-600 rounded-2xl text-zinc-500 dark:text-zinc-400 hover:border-indigo-400 hover:text-indigo-600 dark:hover:border-indigo-500 dark:hover:text-indigo-400 transition-colors flex items-center justify-center gap-2"
        >
          <Plus className="w-4 h-4" /> Ajouter une autre expérience
        </button>
      )}
    </div>
  );
}
