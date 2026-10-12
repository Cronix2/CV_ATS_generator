import type { Metadata } from "next";
import { Schibsted_Grotesk } from "next/font/google";
import "./globals.css";

const ui = Schibsted_Grotesk({ subsets: ["latin"], variable: "--font-ui" });

export const metadata: Metadata = {
  title: "CV ATS depuis LinkedIn",
  description: "Transformez un profil LinkedIn en CV lisible par les ATS.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr" className={ui.variable}>
      <body className="min-h-dvh font-sans antialiased">{children}</body>
    </html>
  );
}
