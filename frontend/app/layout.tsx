import type { Metadata } from "next";
import { Schibsted_Grotesk } from "next/font/google";
import "./globals.css";

const ui = Schibsted_Grotesk({ subsets: ["latin"], variable: "--font-ui" });

export const metadata: Metadata = {
  title: "PasseFiltre · CV qui passe les ATS",
  description: "PasseFiltre transforme un profil LinkedIn en CV qui passe le filtre des ATS.",
  applicationName: "PasseFiltre",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr" className={ui.variable}>
      <body className="min-h-dvh font-sans antialiased">{children}</body>
    </html>
  );
}
