export interface PersonalInfo {
  firstName: string;
  lastName: string;
  email: string;
  phone: string;
  address: string;
  city: string;
  postalCode: string;
  linkedIn: string;
  website: string;
  summary: string;
  title: string;
}

export interface Education {
  id: string;
  school: string;
  degree: string;
  field: string;
  startDate: string;
  endDate: string;
  current: boolean;
  description: string;
  location: string;
}

export interface Experience {
  id: string;
  company: string;
  title: string;
  startDate: string;
  endDate: string;
  current: boolean;
  description: string;
  location: string;
}

export interface Volunteer {
  id: string;
  organization: string;
  role: string;
  startDate: string;
  endDate: string;
  current: boolean;
  description: string;
}

export interface Certification {
  id: string;
  name: string;
  issuer: string;
  date: string;
  url: string;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  technologies: string;
  url: string;
  startDate: string;
  endDate: string;
  current: boolean;
}

export interface Language {
  id: string;
  language: string;
  level: string;
}

export interface CVData {
  personalInfo: PersonalInfo;
  education: Education[];
  experience: Experience[];
  volunteer: Volunteer[];
  projects: Project[];
  skills: string[];
  languages: Language[];
  certifications: Certification[];
}

export const emptyCVData: CVData = {
  personalInfo: {
    firstName: "",
    lastName: "",
    email: "",
    phone: "",
    address: "",
    city: "",
    postalCode: "",
    linkedIn: "",
    website: "",
    summary: "",
    title: "",
  },
  education: [],
  experience: [],
  volunteer: [],
  projects: [],
  skills: [],
  languages: [],
  certifications: [],
};

export type StepId =
  | "welcome"
  | "personal"
  | "education"
  | "experience"
  | "projects"
  | "volunteer"
  | "skills"
  | "languages"
  | "certifications"
  | "preview";

export interface Step {
  id: StepId;
  label: string;
  icon: string;
}

export const STEPS: Step[] = [
  { id: "welcome", label: "Bienvenue", icon: "Home" },
  { id: "personal", label: "Informations", icon: "User" },
  { id: "education", label: "Formation", icon: "GraduationCap" },
  { id: "experience", label: "Expérience", icon: "Briefcase" },
  { id: "projects", label: "Projets", icon: "FolderGit2" },
  { id: "volunteer", label: "Bénévolat", icon: "Heart" },
  { id: "skills", label: "Compétences", icon: "Wrench" },
  { id: "languages", label: "Langues", icon: "Globe" },
  { id: "certifications", label: "Certifications", icon: "Award" },
  { id: "preview", label: "Aperçu", icon: "FileText" },
];
