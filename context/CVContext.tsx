"use client";

import React, { createContext, useContext, useReducer, type ReactNode } from "react";
import { type CVData, emptyCVData } from "@/lib/types";

type Action =
  | { type: "SET_PERSONAL_INFO"; payload: Partial<CVData["personalInfo"]> }
  | { type: "SET_EDUCATION"; payload: CVData["education"] }
  | { type: "SET_EXPERIENCE"; payload: CVData["experience"] }
  | { type: "SET_VOLUNTEER"; payload: CVData["volunteer"] }
  | { type: "SET_PROJECTS"; payload: CVData["projects"] }
  | { type: "SET_SKILLS"; payload: CVData["skills"] }
  | { type: "SET_LANGUAGES"; payload: CVData["languages"] }
  | { type: "SET_CERTIFICATIONS"; payload: CVData["certifications"] }
  | { type: "IMPORT_DATA"; payload: Partial<CVData> }
  | { type: "RESET" };

function cvReducer(state: CVData, action: Action): CVData {
  switch (action.type) {
    case "SET_PERSONAL_INFO":
      return { ...state, personalInfo: { ...state.personalInfo, ...action.payload } };
    case "SET_EDUCATION":
      return { ...state, education: action.payload };
    case "SET_EXPERIENCE":
      return { ...state, experience: action.payload };
    case "SET_VOLUNTEER":
      return { ...state, volunteer: action.payload };
    case "SET_PROJECTS":
      return { ...state, projects: action.payload };
    case "SET_SKILLS":
      return { ...state, skills: action.payload };
    case "SET_LANGUAGES":
      return { ...state, languages: action.payload };
    case "SET_CERTIFICATIONS":
      return { ...state, certifications: action.payload };
    case "IMPORT_DATA":
      return {
        ...state,
        ...action.payload,
        personalInfo: { ...state.personalInfo, ...action.payload.personalInfo },
      };
    case "RESET":
      return emptyCVData;
    default:
      return state;
  }
}

interface CVContextType {
  cvData: CVData;
  dispatch: React.Dispatch<Action>;
}

const CVContext = createContext<CVContextType | undefined>(undefined);

export function CVProvider({ children }: { children: ReactNode }) {
  const [cvData, dispatch] = useReducer(cvReducer, emptyCVData);
  return (
    <CVContext.Provider value={{ cvData, dispatch }}>
      {children}
    </CVContext.Provider>
  );
}

export function useCV() {
  const context = useContext(CVContext);
  if (!context) throw new Error("useCV must be used within CVProvider");
  return context;
}
