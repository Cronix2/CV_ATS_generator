"use client";

import { useState } from "react";
import { STEPS } from "@/lib/types";
import { useCV } from "@/context/CVContext";
import { StepIndicator } from "./StepIndicator";
import { WelcomeStep } from "./steps/WelcomeStep";
import { PersonalInfoStep } from "./steps/PersonalInfoStep";
import { EducationStep } from "./steps/EducationStep";
import { ExperienceStep } from "./steps/ExperienceStep";
import { ProjectsStep } from "./steps/ProjectsStep";
import { VolunteerStep } from "./steps/VolunteerStep";
import { SkillsStep } from "./steps/SkillsStep";
import { LanguagesStep } from "./steps/LanguagesStep";
import { CertificationsStep } from "./steps/CertificationsStep";
import { PreviewStep } from "./steps/PreviewStep";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";

export function StepWizard() {
  const [currentStep, setCurrentStep] = useState(0);
  const { dispatch } = useCV();

  function next() {
    if (currentStep < STEPS.length - 1) setCurrentStep((s) => s + 1);
  }

  function prev() {
    if (currentStep > 0) setCurrentStep((s) => s - 1);
  }

  function reset() {
    dispatch({ type: "RESET" });
    setCurrentStep(0);
  }

  function renderStep() {
    switch (STEPS[currentStep].id) {
      case "welcome":
        return <WelcomeStep onNext={next} />;
      case "personal":
        return <PersonalInfoStep />;
      case "education":
        return <EducationStep />;
      case "experience":
        return <ExperienceStep />;
      case "projects":
        return <ProjectsStep />;
      case "volunteer":
        return <VolunteerStep />;
      case "skills":
        return <SkillsStep />;
      case "languages":
        return <LanguagesStep />;
      case "certifications":
        return <CertificationsStep />;
      case "preview":
        return <PreviewStep onReset={reset} />;
      default:
        return null;
    }
  }

  const isWelcome = currentStep === 0;
  const isPreview = currentStep === STEPS.length - 1;

  return (
    <div className="min-h-[calc(100vh-5rem)] flex flex-col">
      {/* Step Indicator */}
      <div className="sticky top-16 z-30 bg-white/80 dark:bg-zinc-950/80 backdrop-blur-xl border-b border-zinc-200 dark:border-zinc-800 py-4">
        <StepIndicator currentStep={currentStep} />
      </div>

      {/* Step Content */}
      <div className="flex-1 py-8 px-4">
        <div
          key={currentStep}
          className="animate-in fade-in slide-in-from-right-4 duration-300"
        >
          {renderStep()}
        </div>
      </div>

      {/* Navigation */}
      {!isWelcome && (
        <div className="sticky bottom-0 bg-white/80 dark:bg-zinc-950/80 backdrop-blur-xl border-t border-zinc-200 dark:border-zinc-800 py-4 px-4">
          <div className="max-w-2xl mx-auto flex items-center justify-between">
            <button
              onClick={prev}
              className={cn(
                "px-5 py-2.5 rounded-xl font-medium transition-all flex items-center gap-2",
                "border border-zinc-200 dark:border-zinc-700",
                "text-zinc-600 dark:text-zinc-300",
                "hover:bg-zinc-50 dark:hover:bg-zinc-800"
              )}
            >
              <ArrowLeft className="w-4 h-4" /> Précédent
            </button>

            {!isPreview && (
              <button
                onClick={next}
                className={cn(
                  "px-6 py-2.5 rounded-xl font-medium transition-all flex items-center gap-2",
                  "bg-indigo-600 text-white hover:bg-indigo-700",
                  "shadow-lg shadow-indigo-500/20"
                )}
              >
                Suivant <ArrowRight className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
