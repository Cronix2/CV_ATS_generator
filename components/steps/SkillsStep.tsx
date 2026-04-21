"use client";

import { useCV } from "@/context/CVContext";
import { AutocompleteInput } from "@/components/AutocompleteInput";
import { SKILLS } from "@/lib/suggestions";
import { cn } from "@/lib/utils";
import { Plus, X, Wrench } from "lucide-react";
import { useState } from "react";

export function SkillsStep() {
  const { cvData, dispatch } = useCV();
  const [input, setInput] = useState("");

  function addSkill(skill: string) {
    const trimmed = skill.trim();
    if (!trimmed || cvData.skills.includes(trimmed)) return;
    dispatch({ type: "SET_SKILLS", payload: [...cvData.skills, trimmed] });
    setInput("");
  }

  function removeSkill(skill: string) {
    dispatch({
      type: "SET_SKILLS",
      payload: cvData.skills.filter((s) => s !== skill),
    });
  }

  return (
    <div className="space-y-6 max-w-2xl mx-auto">
      <div>
        <h2 className="text-2xl font-bold text-zinc-900 dark:text-white">Compétences</h2>
        <p className="text-zinc-500 dark:text-zinc-400 mt-1">
          Ajoutez vos compétences techniques et humaines. Les systèmes ATS
          recherchent des mots-clés spécifiques.
        </p>
      </div>

      <div className="flex gap-2">
        <div className="flex-1">
          <AutocompleteInput
            label="Ajouter une compétence"
            value={input}
            onChange={setInput}
            suggestions={SKILLS.filter((s) => !cvData.skills.includes(s))}
            placeholder="Tapez pour rechercher (ex: React, Python, Gestion de projet...)"
          />
        </div>
        <div className="flex items-end">
          <button
            onClick={() => addSkill(input)}
            disabled={!input.trim()}
            className={cn(
              "px-4 py-3 rounded-xl font-medium transition-all",
              "bg-indigo-600 hover:bg-indigo-700 text-white",
              "disabled:opacity-50 disabled:cursor-not-allowed"
            )}
          >
            <Plus className="w-5 h-5" />
          </button>
        </div>
      </div>

      {cvData.skills.length === 0 ? (
        <div className="text-center py-12 border-2 border-dashed border-zinc-200 dark:border-zinc-700 rounded-2xl">
          <Wrench className="w-12 h-12 mx-auto text-zinc-300 dark:text-zinc-600 mb-3" />
          <p className="text-zinc-500 dark:text-zinc-400">
            Commencez à taper pour ajouter des compétences
          </p>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          {cvData.skills.map((skill) => (
            <span
              key={skill}
              className={cn(
                "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium",
                "bg-indigo-50 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-300",
                "border border-indigo-200 dark:border-indigo-500/20"
              )}
            >
              {skill}
              <button
                onClick={() => removeSkill(skill)}
                className="p-0.5 hover:bg-indigo-200 dark:hover:bg-indigo-500/20 rounded transition-colors"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </span>
          ))}
        </div>
      )}

      {cvData.skills.length > 0 && (
        <p className="text-sm text-zinc-400">
          {cvData.skills.length} compétence{cvData.skills.length > 1 ? "s" : ""} ajoutée{cvData.skills.length > 1 ? "s" : ""}
        </p>
      )}

      <div className="bg-amber-50 dark:bg-amber-500/5 border border-amber-200 dark:border-amber-500/20 rounded-xl p-4">
        <p className="text-sm text-amber-800 dark:text-amber-300">
          <strong>Conseil ATS :</strong> Utilisez les mêmes termes que ceux présents
          dans les offres d&apos;emploi que vous visez. Les ATS font souvent une correspondance
          exacte des mots-clés.
        </p>
      </div>
    </div>
  );
}
