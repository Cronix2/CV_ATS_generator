import type { Metadata } from "next";
import { ThemeProvider } from "@/components/ThemeProvider";
import { CVProvider } from "@/context/CVContext";
import { ThemeToggle } from "@/components/ThemeToggle";
import { FileText } from "lucide-react";
import "./globals.css";

export const metadata: Metadata = {
  title: "CV ATS Generator — Créez votre CV optimisé",
  description:
    "Générez un CV professionnel compatible ATS en quelques minutes. Import LinkedIn, suggestions intelligentes, export PDF.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="fr" suppressHydrationWarning>
      <body className="min-h-screen bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 antialiased">
        <ThemeProvider>
          <CVProvider>
            <header className="sticky top-0 z-40 bg-white/80 dark:bg-zinc-950/80 backdrop-blur-xl border-b border-zinc-200 dark:border-zinc-800">
              <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-600 to-purple-600 flex items-center justify-center">
                    <FileText className="w-4 h-4 text-white" />
                  </div>
                  <span className="font-bold text-lg hidden sm:block">
                    CV<span className="text-indigo-600 dark:text-indigo-400">ATS</span>
                  </span>
                </div>
                <ThemeToggle />
              </div>
            </header>
            <main className="max-w-6xl mx-auto">{children}</main>
          </CVProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
