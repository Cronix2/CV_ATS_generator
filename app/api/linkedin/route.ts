import { NextResponse } from "next/server";

export async function POST(request: Request) {
  try {
    const { url } = await request.json();

    if (!url || typeof url !== "string") {
      return NextResponse.json({ error: "URL manquante" }, { status: 400 });
    }

    const linkedinPattern = /^https?:\/\/(www\.)?linkedin\.com\/in\/[\w%-]+\/?$/;
    if (!linkedinPattern.test(url)) {
      return NextResponse.json(
        { error: "URL LinkedIn invalide" },
        { status: 400 }
      );
    }

    // ---------------------------------------------------------------
    // In production, connect to a LinkedIn data API such as:
    // - Proxycurl (https://nubela.co/proxycurl)
    // - RapidAPI LinkedIn scrapers
    // - Your own scraping service
    //
    // Example with Proxycurl:
    //   const res = await fetch(
    //     `https://nubela.co/proxycurl/api/v2/linkedin?url=${encodeURIComponent(url)}`,
    //     { headers: { Authorization: `Bearer ${process.env.PROXYCURL_API_KEY}` } }
    //   );
    //   const profile = await res.json();
    //   ... map profile fields to CVData ...
    //
    // For now, we return demo data so the UI flow works end-to-end.
    // ---------------------------------------------------------------

    const slug = url.split("/in/")[1]?.replace(/\/$/, "") || "utilisateur";

    // Decode URL-encoded slug and extract name parts
    const decoded = decodeURIComponent(slug);
    const nameParts = decoded.split("-").filter(Boolean);
    const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
    const firstName = nameParts.length > 0 ? capitalize(nameParts[0]) : "";
    const lastName = nameParts.length > 1 ? nameParts.slice(1).map(capitalize).join(" ") : "";

    const demoData = {
      personalInfo: {
        firstName,
        lastName,
        email: "",
        phone: "",
        title: "",
        city: "",
        postalCode: "",
        linkedIn: url,
        website: "",
        summary: "",
        address: "",
      },
      education: [],
      experience: [],
      skills: [],
      languages: [
        { id: "demo-lang-1", language: "Français", level: "Bilingue / Langue maternelle (C2)" },
      ],
    };

    return NextResponse.json(demoData);
  } catch {
    return NextResponse.json(
      { error: "Erreur serveur lors de l'import" },
      { status: 500 }
    );
  }
}
