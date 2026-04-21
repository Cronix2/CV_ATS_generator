"use client";

import { useCV } from "@/context/CVContext";
import { AutocompleteInput } from "@/components/AutocompleteInput";
import { JOB_TITLES, CITIES } from "@/lib/suggestions";
import { cn } from "@/lib/utils";

export function PersonalInfoStep() {
  const { cvData, dispatch } = useCV();
  const info = cvData.personalInfo;

  function update(field: string, value: string) {
    dispatch({ type: "SET_PERSONAL_INFO", payload: { [field]: value } });
  }

  return (
    <div className="space-y-6 max-w-2xl mx-auto">
      <div>
        <h2 className="text-2xl font-bold text-zinc-900 dark:text-white">
          Informations personnelles
        </h2>
        <p className="text-zinc-500 dark:text-zinc-400 mt-1">
          Ces informations apparaîtront en haut de votre CV.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <InputField
          label="Prénom"
          value={info.firstName}
          onChange={(v) => update("firstName", v)}
          placeholder="Jean"
          required
        />
        <InputField
          label="Nom"
          value={info.lastName}
          onChange={(v) => update("lastName", v)}
          placeholder="Dupont"
          required
        />
      </div>

      <AutocompleteInput
        label="Titre professionnel"
        value={info.title}
        onChange={(v) => update("title", v)}
        suggestions={JOB_TITLES}
        placeholder="Développeur Full Stack"
        required
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <InputField
          label="Email"
          value={info.email}
          onChange={(v) => update("email", v)}
          placeholder="jean.dupont@email.com"
          type="email"
          required
        />
        <InputField
          label="Téléphone"
          value={info.phone}
          onChange={(v) => update("phone", v)}
          placeholder="+33 6 12 34 56 78"
          type="tel"
        />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <InputField
          label="Adresse"
          value={info.address}
          onChange={(v) => update("address", v)}
          placeholder="12 rue de la Paix"
        />
        <AutocompleteInput
          label="Ville"
          value={info.city}
          onChange={(v) => update("city", v)}
          suggestions={CITIES}
          placeholder="Paris"
        />
        <InputField
          label="Code postal"
          value={info.postalCode}
          onChange={(v) => update("postalCode", v)}
          placeholder="75001"
        />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <InputField
          label="LinkedIn"
          value={info.linkedIn}
          onChange={(v) => update("linkedIn", v)}
          placeholder="linkedin.com/in/jean-dupont"
        />
        <InputField
          label="Site web / Portfolio"
          value={info.website}
          onChange={(v) => update("website", v)}
          placeholder="jeandupont.dev"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">
          Résumé professionnel
        </label>
        <textarea
          value={info.summary}
          onChange={(e) => update("summary", e.target.value)}
          rows={4}
          placeholder="Décrivez brièvement votre profil, vos compétences clés et vos objectifs professionnels..."
          className={cn(
            "w-full px-4 py-3 rounded-xl border bg-white dark:bg-zinc-900",
            "border-zinc-200 dark:border-zinc-700",
            "text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500",
            "focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500",
            "transition-all duration-200 resize-none"
          )}
        />
      </div>
    </div>
  );
}

function InputField({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  required = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: string;
  required?: boolean;
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">
        {label}
        {required && <span className="text-rose-500 ml-1">*</span>}
      </label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        required={required}
        className={cn(
          "w-full px-4 py-3 rounded-xl border bg-white dark:bg-zinc-900",
          "border-zinc-200 dark:border-zinc-700",
          "text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500",
          "focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500",
          "transition-all duration-200"
        )}
      />
    </div>
  );
}
