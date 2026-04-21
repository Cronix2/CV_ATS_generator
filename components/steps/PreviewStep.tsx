"use client";

import { useCV } from "@/context/CVContext";
import { formatDate, cn } from "@/lib/utils";
import { Download, RotateCcw, FileCheck } from "lucide-react";
import dynamic from "next/dynamic";
import { useState } from "react";

const PDFDownloadButton = dynamic(
  () => import("./PDFDownloadButton").then((mod) => mod.PDFDownloadButton),
  { ssr: false, loading: () => <DownloadPlaceholder /> }
);

function DownloadPlaceholder() {
  return (
    <div className="px-6 py-3 rounded-xl bg-zinc-200 dark:bg-zinc-700 text-zinc-400 font-medium flex items-center gap-2">
      <Download className="w-5 h-5" />
      Préparation du PDF...
    </div>
  );
}

interface PreviewStepProps {
  onReset: () => void;
}

export function PreviewStep({ onReset }: PreviewStepProps) {
  const { cvData } = useCV();
  const { personalInfo, education, experience, volunteer, projects, skills, languages, certifications } = cvData;
  const [showConfirmReset, setShowConfirmReset] = useState(false);

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-zinc-900 dark:text-white flex items-center gap-2">
            <FileCheck className="w-6 h-6 text-emerald-500" />
            Aperçu de votre CV
          </h2>
          <p className="text-zinc-500 dark:text-zinc-400 mt-1">
            Vérifiez les informations puis téléchargez votre CV au format PDF.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {showConfirmReset ? (
            <div className="flex items-center gap-2">
              <span className="text-sm text-zinc-500">Confirmer ?</span>
              <button
                onClick={() => { onReset(); setShowConfirmReset(false); }}
                className="px-3 py-1.5 rounded-lg bg-rose-600 text-white text-sm hover:bg-rose-700 transition-colors"
              >
                Oui
              </button>
              <button
                onClick={() => setShowConfirmReset(false)}
                className="px-3 py-1.5 rounded-lg bg-zinc-200 dark:bg-zinc-700 text-zinc-600 dark:text-zinc-300 text-sm hover:bg-zinc-300 dark:hover:bg-zinc-600 transition-colors"
              >
                Non
              </button>
            </div>
          ) : (
            <button
              onClick={() => setShowConfirmReset(true)}
              className="px-4 py-2.5 rounded-xl border border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors flex items-center gap-2 text-sm"
            >
              <RotateCcw className="w-4 h-4" /> Recommencer
            </button>
          )}
          <PDFDownloadButton cvData={cvData} />
        </div>
      </div>

      {/* CV Preview Card */}
      <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-2xl shadow-xl overflow-hidden">
        <div className="p-8 sm:p-10 space-y-6">
          {/* Header */}
          <div className="border-b-2 border-zinc-800 dark:border-zinc-200 pb-4">
            <h1 className="text-2xl font-bold text-zinc-900 dark:text-white uppercase tracking-wider">
              {personalInfo.firstName} {personalInfo.lastName}
            </h1>
            {personalInfo.title && (
              <p className="text-zinc-500 dark:text-zinc-400 mt-1">{personalInfo.title}</p>
            )}
            <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-sm text-zinc-600 dark:text-zinc-400">
              {personalInfo.email && <span>{personalInfo.email}</span>}
              {personalInfo.phone && <span>{personalInfo.phone}</span>}
              {personalInfo.city && (
                <span>{personalInfo.city}{personalInfo.postalCode ? ` ${personalInfo.postalCode}` : ""}</span>
              )}
              {personalInfo.linkedIn && <span>{personalInfo.linkedIn}</span>}
              {personalInfo.website && <span>{personalInfo.website}</span>}
            </div>
          </div>

          {/* Summary */}
          {personalInfo.summary && (
            <Section title="Profil">
              <p className="text-sm text-zinc-700 dark:text-zinc-300 leading-relaxed">
                {personalInfo.summary}
              </p>
            </Section>
          )}

          {/* Experience */}
          {experience.length > 0 && (
            <Section title="Expérience Professionnelle">
              {experience.map((exp) => (
                <Entry
                  key={exp.id}
                  title={exp.title}
                  subtitle={`${exp.company}${exp.location ? ` • ${exp.location}` : ""}`}
                  date={`${formatDate(exp.startDate)} — ${exp.current ? "Présent" : formatDate(exp.endDate)}`}
                  description={exp.description}
                />
              ))}
            </Section>
          )}

          {/* Education */}
          {education.length > 0 && (
            <Section title="Formation">
              {education.map((edu) => (
                <Entry
                  key={edu.id}
                  title={`${edu.degree}${edu.field ? ` — ${edu.field}` : ""}`}
                  subtitle={`${edu.school}${edu.location ? ` • ${edu.location}` : ""}`}
                  date={`${formatDate(edu.startDate)} — ${edu.current ? "Présent" : formatDate(edu.endDate)}`}
                  description={edu.description}
                />
              ))}
            </Section>
          )}

          {/* Projects */}
          {projects.length > 0 && (
            <Section title="Projets">
              {projects.map((proj) => (
                <Entry
                  key={proj.id}
                  title={proj.name}
                  subtitle={[proj.technologies, proj.url].filter(Boolean).join(" • ")}
                  date={`${formatDate(proj.startDate)} — ${proj.current ? "Présent" : formatDate(proj.endDate)}`}
                  description={proj.description}
                />
              ))}
            </Section>
          )}

          {/* Skills */}
          {skills.length > 0 && (
            <Section title="Compétences">
              <div className="flex flex-wrap gap-2">
                {skills.map((skill) => (
                  <span
                    key={skill}
                    className="px-2.5 py-1 bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 text-xs rounded-md"
                  >
                    {skill}
                  </span>
                ))}
              </div>
            </Section>
          )}

          {/* Languages */}
          {languages.length > 0 && (
            <Section title="Langues">
              <div className="space-y-1">
                {languages.map((lang) => (
                  <div key={lang.id} className="flex justify-between text-sm">
                    <span className="text-zinc-700 dark:text-zinc-300">{lang.language}</span>
                    <span className="text-zinc-500 dark:text-zinc-400">{lang.level}</span>
                  </div>
                ))}
              </div>
            </Section>
          )}

          {/* Certifications */}
          {certifications.length > 0 && (
            <Section title="Certifications">
              {certifications.map((cert) => (
                <div key={cert.id} className="mb-2">
                  <p className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">
                    {cert.name}
                  </p>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    {cert.issuer}
                    {cert.date ? ` • ${formatDate(cert.date)}` : ""}
                  </p>
                </div>
              ))}
            </Section>
          )}

          {/* Volunteer */}
          {volunteer.length > 0 && (
            <Section title="Bénévolat">
              {volunteer.map((vol) => (
                <Entry
                  key={vol.id}
                  title={vol.role}
                  subtitle={vol.organization}
                  date={`${formatDate(vol.startDate)} — ${vol.current ? "Présent" : formatDate(vol.endDate)}`}
                  description={vol.description}
                />
              ))}
            </Section>
          )}
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-sm font-bold uppercase tracking-wider text-zinc-900 dark:text-white mb-3 pb-1 border-b border-zinc-200 dark:border-zinc-700">
        {title}
      </h3>
      {children}
    </div>
  );
}

function Entry({
  title,
  subtitle,
  date,
  description,
}: {
  title: string;
  subtitle: string;
  date: string;
  description: string;
}) {
  return (
    <div className="mb-4">
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start">
        <p className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">{title}</p>
        <p className="text-xs text-zinc-500 dark:text-zinc-400 whitespace-nowrap">{date}</p>
      </div>
      <p className="text-xs text-zinc-500 dark:text-zinc-400">{subtitle}</p>
      {description && (
        <p className="text-sm text-zinc-700 dark:text-zinc-300 mt-1 whitespace-pre-line leading-relaxed">
          {description}
        </p>
      )}
    </div>
  );
}
