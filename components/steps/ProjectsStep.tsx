"use client";

import { useCV } from "@/context/CVContext";
import { AutocompleteInput } from "@/components/AutocompleteInput";
import { SKILLS } from "@/lib/suggestions";
import { generateId, cn } from "@/lib/utils";
import { Plus, Trash2, FolderGit2 } from "lucide-react";
import type { Project } from "@/lib/types";

export function ProjectsStep() {
  const { cvData, dispatch } = useCV();
  const items = cvData.projects;

  function addItem() {
    const newItem: Project = {
      id: generateId(),
      name: "",
      description: "",
      technologies: "",
      url: "",
      startDate: "",
      endDate: "",
      current: false,
    };
    dispatch({ type: "SET_PROJECTS", payload: [...items, newItem] });
  }

  function updateItem(id: string, updates: Partial<Project>) {
    dispatch({
      type: "SET_PROJECTS",
      payload: items.map((item) => (item.id === id ? { ...item, ...updates } : item)),
    });
  }

  function removeItem(id: string) {
    dispatch({
      type: "SET_PROJECTS",
      payload: items.filter((item) => item.id !== id),
    });
  }

  return (
    <div className="space-y-6 max-w-2xl mx-auto">
      <div>
        <h2 className="text-2xl font-bold text-zinc-900 dark:text-white">
          Projets
        </h2>
        <p className="text-zinc-500 dark:text-zinc-400 mt-1">
          Présentez vos projets personnels, open-source ou académiques.
        </p>
      </div>

      {items.length === 0 && (
        <div className="text-center py-12 border-2 border-dashed border-zinc-200 dark:border-zinc-700 rounded-2xl">
          <FolderGit2 className="w-12 h-12 mx-auto text-zinc-300 dark:text-zinc-600 mb-3" />
          <p className="text-zinc-500 dark:text-zinc-400 mb-4">
            Aucun projet ajouté
          </p>
          <button
            onClick={addItem}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
          >
            <Plus className="w-4 h-4" /> Ajouter un projet
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
              Projet {index + 1}
            </h3>
            <button
              onClick={() => removeItem(item.id)}
              className="p-2 text-zinc-400 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-500/10 rounded-lg transition-colors"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>

          <div>
            <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">
              Nom du projet <span className="text-rose-500">*</span>
            </label>
            <input
              type="text"
              value={item.name}
              onChange={(e) => updateItem(item.id, { name: e.target.value })}
              placeholder="Mon Super Projet"
              className={cn(
                "w-full px-4 py-3 rounded-xl border bg-white dark:bg-zinc-900",
                "border-zinc-200 dark:border-zinc-700 text-zinc-900 dark:text-zinc-100",
                "placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/40",
                "focus:border-indigo-500 transition-all"
              )}
            />
          </div>

          <AutocompleteInput
            label="Technologies utilisées"
            value={item.technologies}
            onChange={(v) => updateItem(item.id, { technologies: v })}
            suggestions={SKILLS}
            placeholder="React, Node.js, PostgreSQL..."
          />

          <div>
            <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">
              URL du projet
            </label>
            <input
              type="url"
              value={item.url}
              onChange={(e) => updateItem(item.id, { url: e.target.value })}
              placeholder="https://github.com/user/project"
              className={cn(
                "w-full px-4 py-3 rounded-xl border bg-white dark:bg-zinc-900",
                "border-zinc-200 dark:border-zinc-700 text-zinc-900 dark:text-zinc-100",
                "placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/40",
                "focus:border-indigo-500 transition-all"
              )}
            />
          </div>

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
                En cours
              </label>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">
              Description
            </label>
            <textarea
              value={item.description}
              onChange={(e) => updateItem(item.id, { description: e.target.value })}
              rows={3}
              placeholder={"• Application web de gestion de tâches\n• Intégration d'une API REST\n• Déploiement sur Vercel..."}
              className={cn(
                "w-full px-4 py-3 rounded-xl border bg-white dark:bg-zinc-900",
                "border-zinc-200 dark:border-zinc-700 text-zinc-900 dark:text-zinc-100",
                "placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/40",
                "focus:border-indigo-500 transition-all resize-none"
              )}
            />
          </div>
        </div>
      ))}

      {items.length > 0 && (
        <button
          onClick={addItem}
          className="w-full py-3 border-2 border-dashed border-zinc-200 dark:border-zinc-700 rounded-2xl text-zinc-500 hover:text-indigo-600 hover:border-indigo-300 dark:hover:border-indigo-700 transition-colors flex items-center justify-center gap-2"
        >
          <Plus className="w-4 h-4" /> Ajouter un autre projet
        </button>
      )}
    </div>
  );
}
