"use client";

import { STEPS } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  Home, User, GraduationCap, Briefcase, Heart,
  Wrench, Globe, Award, FileText, Check, FolderGit2,
} from "lucide-react";

const ICONS: Record<string, React.ElementType> = {
  Home, User, GraduationCap, Briefcase, Heart,
  Wrench, Globe, Award, FileText, FolderGit2,
};

interface StepIndicatorProps {
  currentStep: number;
}

export function StepIndicator({ currentStep }: StepIndicatorProps) {
  return (
    <div className="w-full overflow-x-auto pb-2">
      <div className="flex items-center justify-center gap-1 min-w-max px-4">
        {STEPS.map((step, index) => {
          const Icon = ICONS[step.icon] || FileText;
          const isActive = index === currentStep;
          const isCompleted = index < currentStep;

          return (
            <div key={step.id} className="flex items-center">
              <div className="flex flex-col items-center">
                <div
                  className={cn(
                    "w-10 h-10 rounded-full flex items-center justify-center transition-all duration-300",
                    isActive && "bg-indigo-600 text-white shadow-lg shadow-indigo-500/30 scale-110",
                    isCompleted && "bg-emerald-500 text-white",
                    !isActive && !isCompleted && "bg-zinc-100 dark:bg-zinc-800 text-zinc-400 dark:text-zinc-500"
                  )}
                >
                  {isCompleted ? (
                    <Check className="w-4 h-4" />
                  ) : (
                    <Icon className="w-4 h-4" />
                  )}
                </div>
                <span
                  className={cn(
                    "text-[10px] mt-1 font-medium transition-colors hidden sm:block",
                    isActive && "text-indigo-600 dark:text-indigo-400",
                    isCompleted && "text-emerald-600 dark:text-emerald-400",
                    !isActive && !isCompleted && "text-zinc-400 dark:text-zinc-500"
                  )}
                >
                  {step.label}
                </span>
              </div>
              {index < STEPS.length - 1 && (
                <div
                  className={cn(
                    "w-6 sm:w-10 h-0.5 mx-1 transition-colors duration-300 rounded-full",
                    index < currentStep
                      ? "bg-emerald-500"
                      : "bg-zinc-200 dark:bg-zinc-700"
                  )}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
