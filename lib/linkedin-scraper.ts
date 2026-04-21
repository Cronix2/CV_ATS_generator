import puppeteer, { type Browser, type Page } from "puppeteer-core";
import { writeFileSync, mkdirSync } from "fs";
import { join } from "path";

const CHROME_PATH =
  process.env.CHROME_PATH ||
  "C:/Program Files/Google/Chrome/Application/chrome.exe";

// ---- Types ----

export interface ScrapeProgress {
  step: string;
  percent: number;
  detail?: string;
}

export interface MfaChallengeContext {
  reason: string;
  url: string;
}

export interface ScrapeResult {
  personalInfo: {
    firstName: string;
    lastName: string;
    email: string;
    phone: string;
    title: string;
    city: string;
    postalCode: string;
    linkedIn: string;
    website: string;
    summary: string;
    address: string;
  };
  education: Array<{
    id: string;
    school: string;
    degree: string;
    field: string;
    startDate: string;
    endDate: string;
    current: boolean;
    description: string;
    location: string;
  }>;
  experience: Array<{
    id: string;
    company: string;
    title: string;
    startDate: string;
    endDate: string;
    current: boolean;
    description: string;
    location: string;
  }>;
  volunteer: Array<{
    id: string;
    organization: string;
    role: string;
    startDate: string;
    endDate: string;
    current: boolean;
    description: string;
  }>;
  projects: Array<{
    id: string;
    name: string;
    description: string;
    technologies: string;
    url: string;
    startDate: string;
    endDate: string;
    current: boolean;
  }>;
  skills: string[];
  languages: Array<{
    id: string;
    language: string;
    level: string;
  }>;
  certifications: Array<{
    id: string;
    name: string;
    issuer: string;
    date: string;
    url: string;
  }>;
}

// ---- User-Agent rotation ----

const USER_AGENTS = [
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
];

function randomUA(): string {
  return USER_AGENTS[Math.floor(Math.random() * USER_AGENTS.length)];
}

function genId(): string {
  return Math.random().toString(36).slice(2, 10);
}

// ---- Helpers for date parsing ----

const MONTH_MAP: Record<string, string> = {
  janv: "01", janvier: "01", jan: "01",
  févr: "02", février: "02", feb: "02", fév: "02",
  mars: "03", mar: "03",
  avr: "04", avril: "04", apr: "04",
  mai: "05", may: "05",
  juin: "06", jun: "06",
  juil: "07", juillet: "07", jul: "07",
  août: "08", aug: "08", aout: "08",
  sept: "09", septembre: "09", sep: "09",
  oct: "10", octobre: "10",
  nov: "11", novembre: "11",
  déc: "12", décembre: "12", dec: "12",
};

function parseLinkedInDate(raw: string): string {
  if (!raw) return "";
  const cleaned = raw.trim().toLowerCase();

  const yearOnly = cleaned.match(/^(\d{4})$/);
  if (yearOnly) return `${yearOnly[1]}-01`;

  for (const [key, val] of Object.entries(MONTH_MAP)) {
    const re = new RegExp(`${key}\\.?\\s*(\\d{4})`);
    const m = cleaned.match(re);
    if (m) return `${m[1]}-${val}`;
  }

  const enMonths: Record<string, string> = {
    january: "01", february: "02", march: "03", april: "04",
    may: "05", june: "06", july: "07", august: "08",
    september: "09", october: "10", november: "11", december: "12",
  };
  for (const [key, val] of Object.entries(enMonths)) {
    if (cleaned.includes(key)) {
      const ym = cleaned.match(/(\d{4})/);
      if (ym) return `${ym[1]}-${val}`;
    }
  }

  return "";
}

function parseDateRange(raw: string): { start: string; end: string; current: boolean } {
  if (!raw) return { start: "", end: "", current: false };
  const isCurrent =
    raw.toLowerCase().includes("présent") ||
    raw.toLowerCase().includes("present") ||
    raw.toLowerCase().includes("aujourd");
  const parts = raw.split(/\s*[-–]\s*/);
  return {
    start: parseLinkedInDate(parts[0] || ""),
    end: isCurrent ? "" : parseLinkedInDate(parts[1] || ""),
    current: isCurrent,
  };
}

function parseDateRangeFromAnyText(raw: string): { start: string; end: string; current: boolean } {
  if (!raw) return { start: "", end: "", current: false };

  const compact = raw.replace(/\s+/g, " ").trim();
  const current = /présent|present|aujourd|current/i.test(compact);

  const monthYearRegex =
    /(janv\.?|janvier|jan|févr\.?|février|fév\.?|feb\.?|mars|mar\.?|avr\.?|avril|apr\.?|mai|may|juin|jun\.?|juil\.?|juillet|jul\.?|août|aout|aug\.?|sept\.?|septembre|sep\.?|oct\.?|octobre|nov\.?|novembre|déc\.?|décembre|dec\.?|january|february|march|april|june|july|august|september|october|november|december)\s*\.?\s*\d{4}/gi;

  const found = compact.match(monthYearRegex) || [];

  if (found.length >= 2) {
    return {
      start: parseLinkedInDate(found[0]),
      end: current ? "" : parseLinkedInDate(found[1]),
      current,
    };
  }

  if (found.length === 1) {
    return {
      start: parseLinkedInDate(found[0]),
      end: "",
      current,
    };
  }

  const years = compact.match(/\b\d{4}\b/g) || [];
  if (years.length >= 2) {
    return {
      start: parseLinkedInDate(years[0]),
      end: current ? "" : parseLinkedInDate(years[1]),
      current,
    };
  }

  if (years.length === 1) {
    return {
      start: parseLinkedInDate(years[0]),
      end: "",
      current,
    };
  }

  return { start: "", end: "", current };
}

function isLikelyDateLine(raw: string): boolean {
  if (!raw) return false;
  return /\d{4}/.test(raw) || /présent|present|aujourd/i.test(raw);
}

function parseExperienceEntry(texts: string[]): {
  title: string;
  company: string;
  startDate: string;
  endDate: string;
  current: boolean;
  description: string;
  location: string;
} {
  // Extract hints injected by the DOM walker for grouped roles
  let hintCompany = "";
  let hintLocation = "";
  const filtered: string[] = [];
  for (const t of texts) {
    if (t.startsWith("__company__:")) {
      hintCompany = t.slice("__company__:".length).trim();
      continue;
    }
    if (t.startsWith("__location__:")) {
      hintLocation = t.slice("__location__:".length).trim();
      continue;
    }
    filtered.push(t);
  }

  const cleaned = filtered
    .map((t) => t.replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .filter((t, idx, arr) => arr.indexOf(t) === idx);

  const dateIdx = cleaned.findIndex((t) => isLikelyDateLine(t));
  const joined = cleaned.join(" ");
  const dateRaw = dateIdx >= 0 ? cleaned[dateIdx] : joined;
  const { start, end, current } = parseDateRangeFromAnyText(dateRaw);

  // Title = first line (most reliable on new UI)
  let title = cleaned[0] || "";
  // If title line looks like a date, pick next non-date
  if (isLikelyDateLine(title)) {
    title = cleaned.find((t) => !isLikelyDateLine(t)) || title;
  }

  let company = "";
  // Format "Title – Company" (common for grouped roles)
  if (title.includes(" – ")) {
    const [left, right] = title.split(" – ");
    title = (left || "").trim();
    if (!hintCompany) company = (right || "").trim();
    // else: keep hintCompany and drop the suffix (redundant)
  } else if (title.includes(" at ")) {
    const [left, right] = title.split(" at ");
    title = (left || "").trim();
    company = (right || "").trim();
  }

  // If we have the company hint from the parent entity (grouped roles), use it
  if (hintCompany) company = hintCompany;

  // Otherwise, company is usually line after title in format "Company · EmploymentType"
  if (!company) {
    const subtitle = cleaned.find(
      (t, i) => i > 0 && i !== dateIdx && !isLikelyDateLine(t) && t.length < 180,
    );
    if (subtitle) {
      // "Company · CDI" or "Company · Temps plein"
      const parts = subtitle.split(/\s+·\s+/);
      company = (parts[0] || "").trim();
    }
  }

  // Location: hint first, else find a line looking like a location
  let location = hintLocation;
  if (!location) {
    location =
      cleaned.find(
        (t) =>
          t.length <= 140 &&
          /france|paris|lyon|marseille|toulouse|bordeaux|nantes|lille|rennes|t[ée]l[ée]travail|remote|hybride|sur site/i.test(
            t,
          ) &&
          !isLikelyDateLine(t),
      ) || "";
  }

  // Build description from lines that aren't title/company/date/location/skills-summary
  const origTitleLine = cleaned[0] || "";
  const skip = new Set<string>([title, company, location, cleaned[dateIdx] || "", origTitleLine]);
  const descParts = cleaned.filter((t) => {
    if (!t) return false;
    if (skip.has(t)) return false;
    if (isLikelyDateLine(t)) return false;
    if (t.length <= 25) return false;
    // Skip subtitle like "Company · CDI"
    if (company && t.startsWith(company + " ·")) return false;
    // Skip skill summary lines ("Cyber Threat Intelligence (CTI), ... et 3 compétences de plus")
    if (/\bet\s+\d+\s+comp[ée]tences?\s+de\s+plus\b/i.test(t)) return false;
    if (/\band\s+\d+\s+more\s+skills?\b/i.test(t)) return false;
    // Skip image/document filenames
    if (/\.(png|jpg|jpeg|gif|webp|svg|pdf|docx?|pptx?)\b/i.test(t)) return false;
    return true;
  }).map((t) =>
    t
      .replace(/…\s*plus\s*$/i, "")
      .replace(/\s+…\s*$/, "")
      .trim(),
  ).filter(Boolean);

  return {
    title,
    company,
    startDate: start,
    endDate: end,
    current,
    description: descParts.join("\n"),
    location,
  };
}

// ---- Delay helpers ----

function wait(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

function randomDelay(min: number, max: number): Promise<void> {
  return wait(min + Math.random() * (max - min));
}

// ---- Scroll page to trigger lazy loading ----

async function autoScroll(page: Page): Promise<void> {
  await page.evaluate(async () => {
    await new Promise<void>((resolve) => {
      let totalHeight = 0;
      const distance = 300;
      const timer = setInterval(() => {
        const scrollHeight = document.body.scrollHeight;
        window.scrollBy(0, distance);
        totalHeight += distance;
        if (totalHeight >= scrollHeight + 1000) {
          clearInterval(timer);
          resolve();
        }
      }, 200);
      setTimeout(() => { clearInterval(timer); resolve(); }, 25000);
    });
  });
  // Scroll back to top
  await page.evaluate(() => window.scrollTo(0, 0));
  await wait(500);
}

// ---- Click all expand/see-more buttons ----

async function clickAllSeeMore(page: Page): Promise<void> {
  // Multiple rounds since clicking one button might reveal others
  for (let round = 0; round < 3; round++) {
    const clicked = await page.evaluate(() => {
      let count = 0;
      const selectors = [
        'button.inline-show-more-text__button',
        'button[aria-label*="voir plus"]',
        'button[aria-label*="see more"]',
        'button[aria-label*="Voir plus"]',
        'button[aria-label*="See more"]',
        'button[aria-label*="more"]',
        '.pvs-list__footer-wrapper button',
      ];
      for (const sel of selectors) {
        document.querySelectorAll(sel).forEach((btn) => {
          (btn as HTMLElement).click();
          count++;
        });
      }
      return count;
    });
    if (clicked === 0) break;
    await wait(800);
  }
}

// ---- Save debug screenshot ----

function saveDebug(filename: string, content: string): void {
  try {
    const dir = join(process.cwd(), "debug");
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, filename), content, "utf-8");
  } catch {
    // Ignore debug save errors
  }
}

// ---- Find a section by ID, componentkey or heading text ----

// Component keys used by LinkedIn's new SDUI profile (2024-2026 UI)
const SECTION_COMPONENT_KEYS: Record<string, string[]> = {
  experience: ["ExperienceTopLevelSection"],
  education: ["EducationTopLevelSection"],
  certifications: ["CertificationTopLevel"],
  projects: ["Projects"],
  volunteer: ["VolunteerExperienceTopLevel"],
  skills: ["Skills"],
  languages: ["LanguageTopLevel"],
  honors: ["HonorsTopLevel"],
  courses: ["CourseTopLevelSection"],
  publications: ["PublicationTopLevelSection"],
  organizations: ["Organizations"],
};

async function findAndExtractSection(
  page: Page,
  ids: string[],
  headings: string[],
  componentKeys: string[] = [],
): Promise<Array<string[]>> {
  return page.evaluate(
    (ids: string[], headings: string[], componentKeys: string[]) => {
      const cleanLine = (raw: string): string =>
        raw.replace(/\s+/g, " ").replace(/\u200b/g, "").trim();

      const NOISE_EXACT = new Set<string>([
        "voir plus", "see more", "voir moins", "show less",
        "suivre", "following", "se connecter", "connect",
        "tout afficher", "show all", "afficher tout", "voir tout",
        "afficher le diplôme", "show credential", "plus",
        "afficher toutes les licences", "afficher toutes les compétences",
        "tout", "all",
        "autres contributeurs", "voir tous les contributeurs",
        "plus d'informations", "plus d infos", "more info",
        "identifiant du diplôme", "credential id",
      ]);
      const NOISE_PREFIX = [
        "afficher toutes les ",
        "afficher tous les ",
        "show all ",
        "voir les ",
        "voir le ",
      ];

      const removeNoise = (lines: string[]): string[] => {
        const seen = new Set<string>();
        const out: string[] = [];
        for (const l of lines) {
          const v = cleanLine(l);
          if (!v || v.length < 2) continue;
          if (/^[·•\-–—|]+$/.test(v)) continue;
          const low = v.toLowerCase();
          if (NOISE_EXACT.has(low)) continue;
          if (NOISE_PREFIX.some((p) => low.startsWith(p))) continue;
          if (seen.has(v)) continue;
          seen.add(v);
          out.push(v);
        }
        return out;
      };

      // Gather text lines from an item container, preserving DOM order
      const extractItemLines = (item: Element): string[] => {
        const lines: string[] = [];
        const seenNodes = new WeakSet<Node>();

        // Walk the subtree in document order and pick text-bearing leaves
        const walker = document.createTreeWalker(item, NodeFilter.SHOW_ELEMENT);
        const pushText = (el: Element) => {
          const t = (el.textContent || "").trim();
          if (t && t.length < 4000) lines.push(t);
        };

        // First pass: p elements, aria-hidden spans, expandable text boxes, and
        // anchors (for "Tout afficher" → already filtered by noise list).
        const textSelectors = [
          "p",
          'span[aria-hidden="true"]',
          '[data-testid="expandable-text-box"]',
          "h3",
          "h4",
        ];
        // We avoid double counting nested duplicates (e.g. aria-hidden inside a <p>)
        const captured = new Set<string>();
        for (const sel of textSelectors) {
          const els = item.querySelectorAll(sel);
          els.forEach((el) => {
            if (seenNodes.has(el)) return;
            seenNodes.add(el);
            const t = (el.textContent || "").replace(/\s+/g, " ").trim();
            if (!t) return;
            if (captured.has(t)) return;
            captured.add(t);
            lines.push(t);
            if (walker) void walker; // tsc no-op
            if (pushText) void pushText;
          });
        }

        // Fallback: innerText split if we got nothing
        if (lines.length === 0) {
          const visual = ((item as HTMLElement).innerText || "")
            .split("\n")
            .map((s) => s.trim())
            .filter(Boolean);
          lines.push(...visual);
        }

        return removeNoise(lines);
      };

      // Collect structured items from a section element (works with old and new UIs)
      const collectItems = (root: Element): Array<string[]> => {
        const out: Array<string[]> = [];

        // --- Strategy A: entity-collection-item containers (new Experience UI) ---
        const entityItems = Array.from(
          root.querySelectorAll('div[componentkey^="entity-collection-item"]'),
        );
        if (entityItems.length > 0) {
          for (const ci of entityItems) {
            // Grouped roles: nested <ul><li> inside the entity item
            const nestedLis = Array.from(ci.querySelectorAll(":scope ul > li"));
            if (nestedLis.length > 0) {
              // Extract parent (company) context without the nested list
              const clone = ci.cloneNode(true) as Element;
              clone.querySelectorAll("ul").forEach((u) => u.remove());
              const parentTexts = extractItemLines(clone);
              const companyName = parentTexts[0] || "";
              const parentLocation =
                parentTexts.find((t) =>
                  /france|paris|lyon|marseille|toulouse|hybride|remote|sur site|t[ée]l[ée]travail/i.test(
                    t,
                  ),
                ) || "";

              for (const li of nestedLis) {
                const liTexts = extractItemLines(li);
                if (liTexts.length > 0) {
                  const enriched = [...liTexts];
                  if (companyName) enriched.push("__company__:" + companyName);
                  if (parentLocation) enriched.push("__location__:" + parentLocation);
                  out.push(enriched);
                }
              }
            } else {
              const texts = extractItemLines(ci);
              if (texts.length > 0) out.push(texts);
            }
          }
          return out;
        }

        // --- Strategy B: split by <hr role="presentation"> at the appropriate level ---
        // Find the innermost container whose direct children include multiple hrs
        // (this is where item blocks live in the new UI).
        let itemContainer: Element | null = null;
        const allDivs = Array.from(root.querySelectorAll("div"));
        let bestCount = 0;
        for (const c of allDivs) {
          const childHrs = Array.from(c.children).filter(
            (ch) =>
              ch.tagName === "HR" &&
              (ch.getAttribute("role") === "presentation" || ch.getAttribute("role") === null),
          ).length;
          if (childHrs > bestCount) {
            bestCount = childHrs;
            itemContainer = c;
          }
        }

        if (itemContainer && bestCount >= 1) {
          const children = Array.from(itemContainer.children);
          let currentBlock: Element[] = [];
          const blocks: Element[][] = [];
          for (const ch of children) {
            if (ch.tagName === "HR") {
              if (currentBlock.length > 0) {
                blocks.push(currentBlock);
                currentBlock = [];
              }
            } else if (ch.tagName !== "H2") {
              currentBlock.push(ch);
            }
          }
          if (currentBlock.length > 0) blocks.push(currentBlock);

          for (const block of blocks) {
            const wrapper = document.createElement("div");
            for (const el of block) wrapper.appendChild(el.cloneNode(true));
            const texts = extractItemLines(wrapper);
            // Must contain at least something that looks like a heading (non-trivial)
            if (texts.length > 0 && texts.some((t) => t.length >= 2)) {
              out.push(texts);
            }
          }
          if (out.length > 0) return out;
        }

        // --- Strategy C: legacy <ul><li> items ---
        let items: Element[] = Array.from(
          root.querySelectorAll(
            ":scope > .pvs-list__outer-container > ul > li, :scope > div > div > ul > li",
          ),
        );
        if (items.length === 0) {
          const mainUl = root.querySelector("ul");
          if (mainUl) {
            items = Array.from(mainUl.children).filter(
              (el) => el.tagName === "LI",
            ) as Element[];
          }
        }
        if (items.length === 0) {
          items = Array.from(root.querySelectorAll("li"));
        }
        if (items.length === 0) {
          items = Array.from(
            root.querySelectorAll(
              ".pvs-entity, [data-view-name*='profile-component-entity']",
            ),
          );
        }
        for (const li of items) {
          const texts = extractItemLines(li);
          if (texts.length > 0) out.push(texts);
        }

        if (out.length > 0) return out;

        // --- Strategy D: repeated sibling divs with UUID componentkey (SDUI projects) ---
        const uuidRe = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
        const allContainers = Array.from(root.querySelectorAll("div"));
        let bestUuidParent: Element | null = null;
        let bestUuidKids: Element[] = [];
        for (const p of allContainers) {
          const uuidKids = Array.from(p.children).filter((c) => {
            const ck = c.getAttribute("componentkey") || "";
            return uuidRe.test(ck);
          });
          if (uuidKids.length > bestUuidKids.length) {
            bestUuidKids = uuidKids;
            bestUuidParent = p;
          }
        }
        if (bestUuidParent && bestUuidKids.length >= 2) {
          for (const kid of bestUuidKids) {
            const texts = extractItemLines(kid);
            if (texts.length > 0) out.push(texts);
          }
          if (out.length > 0) return out;
        }

        // --- Strategy E (last resort): all <p> in DOM order, split on date ranges ---
        const pTexts = Array.from(root.querySelectorAll("p, h3, h4"))
          .filter((p) => !p.closest('[role="tab"], [role="tablist"]'))
          .map((p) => (p.textContent || "").replace(/\s+/g, " ").trim())
          .filter(Boolean);
        const psCleaned = removeNoise(pTexts);
        const isDateLineE = (t: string) =>
          /\b(19|20)\d{2}\b/.test(t) &&
          (/-|–|—|à|au|aujourd|pr[ée]sent|present|to\b/i.test(t));
        if (psCleaned.length > 0) {
          const dateIdxE: number[] = [];
          psCleaned.forEach((t, i) => {
            if (isDateLineE(t)) dateIdxE.push(i);
          });
          if (dateIdxE.length >= 1) {
            let startE = 0;
            for (let k = 0; k < dateIdxE.length; k++) {
              const nxt = dateIdxE[k + 1];
              const endE =
                nxt != null
                  ? Math.max(startE + 1, nxt - 2)
                  : psCleaned.length;
              const blk = psCleaned.slice(startE, endE);
              if (blk.length > 0) out.push(blk);
              startE = endE;
            }
          }
        }

        return out;
      };

      // --- Locate the section ---
      // IMPORTANT: LinkedIn's new SDUI UI reuses card-template componentkeys
      // with misleading names (e.g. a card keyed "...CjcProjects" can actually
      // contain CERTIFICATIONS). Always match by the visible <h2> heading first.
      let section: Element | null = null;

      // 1) By h2 heading text (authoritative)
      {
        const allSections = document.querySelectorAll("section");
        for (const s of allSections) {
          const h2 = s.querySelector("h2");
          const hText = (h2?.textContent?.trim() || "").toLowerCase();
          if (!hText) continue;
          for (const heading of headings) {
            if (hText.includes(heading.toLowerCase())) {
              section = s;
              break;
            }
          }
          if (section) break;
        }
      }

      // 2) By anchor id
      if (!section) {
        for (const id of ids) {
          const anchor = document.getElementById(id);
          if (anchor) {
            section = anchor.closest("section");
            if (section) break;
          }
        }
      }

      // 3) By componentkey (last resort — unreliable on new UI)
      if (!section) {
        const sections = Array.from(document.querySelectorAll("section"));
        for (const s of sections) {
          const ck = s.getAttribute("componentkey") || "";
          if (!ck) continue;
          for (const key of componentKeys) {
            if (ck.toLowerCase().includes(key.toLowerCase())) {
              section = s;
              break;
            }
          }
          if (section) break;
        }
      }

      if (!section) return [];
      const raw = collectItems(section);

      // Filter and split
      const textsLookLikePerson = (texts: string[]): boolean => {
        for (const t of texts) {
          if (/·\s*(1er|2e|3e(\s*et\s*\+)?|1st|2nd|3rd(\+)?)/i.test(t)) return true;
        }
        return false;
      };
      const isDateLine = (t: string) =>
        /\b(19|20)\d{2}\b/.test(t) &&
        (/-|–|—|à|au|aujourd|présent|present|to\b/i.test(t));
      const splitOnDateRanges = (texts: string[]): string[][] => {
        const dateIndices: number[] = [];
        texts.forEach((t, i) => {
          if (isDateLine(t)) dateIndices.push(i);
        });
        if (dateIndices.length <= 1) return [texts];
        const items: string[][] = [];
        let start = 0;
        for (let k = 0; k < dateIndices.length; k++) {
          const nextDateIdx = dateIndices[k + 1];
          // For the next item, reserve up to 2 lines preceding its date as its header
          const end =
            nextDateIdx != null
              ? Math.max(start + 1, nextDateIdx - 2)
              : texts.length;
          const block = texts.slice(start, end);
          if (block.length > 0) items.push(block);
          start = end;
        }
        return items.length > 0 ? items : [texts];
      };
      const final: Array<string[]> = [];
      for (const entry of raw) {
        if (textsLookLikePerson(entry)) continue;
        const split = splitOnDateRanges(entry);
        for (const s of split) {
          if (s.length === 0) continue;
          if (textsLookLikePerson(s)) continue;
          final.push(s);
        }
      }
      return final;
    },
    ids,
    headings,
    componentKeys,
  );
}

// ---- Navigate to a /details/ subpage and scrape ----

async function scrapeDetailsPage(
  page: Page,
  profileUrl: string,
  detailPath: string,
): Promise<Array<string[]>> {
  const url = profileUrl.replace(/\/$/, "") + `/details/${detailPath}/`;
  return scrapeDetailsPageByUrl(page, url);
}

async function scrapeDetailsPageByUrl(
  page: Page,
  url: string,
): Promise<Array<string[]>> {
  try {
    await page.goto(url, { waitUntil: "networkidle2", timeout: 20000 });
    await randomDelay(1500, 2500);
    await autoScroll(page);
    await clickAllSeeMore(page);
    // Repeated scroll-until-stable to load lazy / paginated items
    let lastHeight = 0;
    for (let i = 0; i < 6; i++) {
      await autoScroll(page);
      await clickAllSeeMore(page);
      const h = await page
        .evaluate(() => document.body.scrollHeight)
        .catch(() => 0);
      if (h === lastHeight) break;
      lastHeight = h;
      await randomDelay(400, 800);
    }
    await randomDelay(500, 1000);

    // Check we're actually on a details page (not redirected to login)
    const pageUrl = page.url();
    if (pageUrl.includes("login") || pageUrl.includes("authwall")) {
      return [];
    }

    // Check for LinkedIn's "Page non trouvée" / 404 error page
    const is404 = await page.evaluate(() => {
      const body = (document.body.textContent || "").toLowerCase();
      return (
        body.includes("veuillez vérifier votre url") ||
        body.includes("page non trouvée") ||
        body.includes("this page doesn") ||
        body.includes("page not found") ||
        body.length < 500
      );
    });
    if (is404) return [];

    return await page.evaluate(() => {
      const cleanLine = (raw: string): string =>
        raw.replace(/\s+/g, " ").replace(/\u200b/g, "").trim();

      const NOISE_EXACT = new Set<string>([
        "voir plus", "see more", "voir moins", "show less",
        "suivre", "following", "se connecter", "connect",
        "tout afficher", "show all", "afficher tout", "voir tout",
        "afficher le diplôme", "show credential", "plus",
        "tout", "all",
        "connaissances du secteur", "outils et technologie",
        "compétences interpersonnelles", "industry knowledge",
        "tools & technologies", "interpersonal skills",
        "autres contributeurs", "voir tous les contributeurs",
        "plus d'informations", "plus d infos", "more info",
        "identifiant du diplôme", "credential id",
      ]);
      const NOISE_PREFIX = [
        "afficher toutes les ",
        "afficher tous les ",
        "show all ",
        "voir les ",
        "voir le ",
      ];

      const removeNoise = (lines: string[]): string[] => {
        const seen = new Set<string>();
        const out: string[] = [];
        for (const l of lines) {
          const v = cleanLine(l);
          if (!v || v.length < 2) continue;
          if (/^[·•\-–—|]+$/.test(v)) continue;
          const low = v.toLowerCase();
          if (NOISE_EXACT.has(low)) continue;
          if (NOISE_PREFIX.some((p) => low.startsWith(p))) continue;
          if (seen.has(v)) continue;
          seen.add(v);
          out.push(v);
        }
        return out;
      };

      // Detect a person-card (connection suggestion / "People you may know")
      const isPersonCard = (item: Element): boolean => {
        const txt = (item.textContent || "").toLowerCase();
        if (/·\s*(1er|2e|3e(\s*et\s*\+)?|1st|2nd|3rd(\+)?)/i.test(txt)) return true;
        const btns = item.querySelectorAll("button");
        for (const b of btns) {
          const bt = (b.textContent || "").trim().toLowerCase();
          if (bt === "se connecter" || bt === "connect" || bt === "suivre" || bt === "follow" || bt === "message") return true;
        }
        return false;
      };

      const textsLookLikePerson = (texts: string[]): boolean => {
        for (const t of texts) {
          if (/·\s*(1er|2e|3e(\s*et\s*\+)?|1st|2nd|3rd(\+)?)/i.test(t)) return true;
        }
        return false;
      };

      // Split a merged item containing multiple date-range lines into separate items
      const splitOnDateRanges = (texts: string[]): string[][] => {
        const isDateLine = (t: string) =>
          /\b(19|20)\d{2}\b/.test(t) &&
          (/-|–|—|à|au|aujourd|présent|present|to\b/i.test(t));
        const dateIndices: number[] = [];
        texts.forEach((t, i) => {
          if (isDateLine(t)) dateIndices.push(i);
        });
        if (dateIndices.length <= 1) return [texts];
        const items: string[][] = [];
        let start = 0;
        for (let k = 0; k < dateIndices.length; k++) {
          const nextDateIdx = dateIndices[k + 1];
          const end =
            nextDateIdx != null
              ? Math.max(start + 1, nextDateIdx - 2)
              : texts.length;
          const block = texts.slice(start, end);
          if (block.length > 0) items.push(block);
          start = end;
        }
        return items.length > 0 ? items : [texts];
      };

      const extractItemLines = (item: Element): string[] => {
        const lines: string[] = [];
        const captured = new Set<string>();
        const textSelectors = [
          "p",
          'span[aria-hidden="true"]',
          '[data-testid="expandable-text-box"]',
          "h3",
          "h4",
        ];
        for (const sel of textSelectors) {
          const els = item.querySelectorAll(sel);
          els.forEach((el) => {
            const t = (el.textContent || "").replace(/\s+/g, " ").trim();
            if (!t) return;
            if (captured.has(t)) return;
            captured.add(t);
            lines.push(t);
          });
        }
        if (lines.length === 0) {
          const visual = ((item as HTMLElement).innerText || "")
            .split("\n")
            .map((s) => s.trim())
            .filter(Boolean);
          lines.push(...visual);
        }
        return removeNoise(lines);
      };

      const collectItems = (root: Element | Document): Array<string[]> => {
        // Restrict to <main> if present (avoids the right sidebar "People you may know")
        let scope: Element | null = null;
        const doc = (root as Document).body ? (root as Document) : document;
        scope = doc.querySelector("main");
        if (!scope) {
          scope = (root as Document).body
            ? ((root as Document).body as Element)
            : (root as Element);
        }
        const out: Array<string[]> = [];

        // Strategy A: entity-collection-item (new Experience-like details pages)
        const entityItems = Array.from(
          scope.querySelectorAll('div[componentkey^="entity-collection-item"]'),
        ).filter((el) => !isPersonCard(el));
        if (entityItems.length > 0) {
          for (const ci of entityItems) {
            const nestedLis = Array.from(ci.querySelectorAll(":scope ul > li"));
            if (nestedLis.length > 0) {
              const clone = ci.cloneNode(true) as Element;
              clone.querySelectorAll("ul").forEach((u) => u.remove());
              const parentTexts = extractItemLines(clone);
              const companyName = parentTexts[0] || "";
              const parentLocation =
                parentTexts.find((t) =>
                  /france|paris|lyon|marseille|toulouse|hybride|remote|sur site|t[ée]l[ée]travail/i.test(
                    t,
                  ),
                ) || "";
              for (const li of nestedLis) {
                const liTexts = extractItemLines(li);
                if (liTexts.length > 0) {
                  const enriched = [...liTexts];
                  if (companyName) enriched.push("__company__:" + companyName);
                  if (parentLocation)
                    enriched.push("__location__:" + parentLocation);
                  out.push(enriched);
                }
              }
            } else {
              const texts = extractItemLines(ci);
              if (texts.length > 0) out.push(texts);
            }
          }
          if (out.length > 0) return out;
        }

        // Strategy B: split by <hr role="presentation"> in the best container
        // Scope is already <main>, so look inside its descendants.
        const candidates: Element[] = Array.from(
          scope.querySelectorAll("div, section, ul"),
        );
        let best: Element | null = null;
        let bestCount = 0;
        for (const c of candidates) {
          // Reject containers inside aside/complementary regions
          if (c.closest('aside, [role="complementary"]')) continue;
          const childHrs = Array.from(c.children).filter(
            (ch) => ch.tagName === "HR",
          ).length;
          if (childHrs > bestCount) {
            bestCount = childHrs;
            best = c;
          }
        }
        if (best && bestCount >= 1) {
          const children = Array.from(best.children);
          let currentBlock: Element[] = [];
          const blocks: Element[][] = [];
          for (const ch of children) {
            if (ch.tagName === "HR") {
              if (currentBlock.length > 0) {
                blocks.push(currentBlock);
                currentBlock = [];
              }
            } else {
              currentBlock.push(ch);
            }
          }
          if (currentBlock.length > 0) blocks.push(currentBlock);
          for (const block of blocks) {
            const wrapper = document.createElement("div");
            for (const el of block) wrapper.appendChild(el.cloneNode(true));
            // Skip blocks that are tab bars (only contain <button>/<a role=tab>)
            const roleTab = wrapper.querySelector('[role="tab"]');
            if (roleTab && wrapper.textContent && wrapper.textContent.length < 200) {
              continue;
            }
            if (isPersonCard(wrapper)) continue;
            const texts = extractItemLines(wrapper);
            if (texts.length > 0) out.push(texts);
          }
          if (out.length > 0) return out;
        }

        // Strategy C: legacy LinkedIn selectors
        let listItems: Element[] = Array.from(
          scope.querySelectorAll(".pvs-list__paged-list-item"),
        );
        if (listItems.length === 0) {
          listItems = Array.from(
            scope.querySelectorAll(".pvs-list__outer-container ul > li"),
          );
        }
        if (listItems.length === 0) {
          listItems = Array.from(
            scope.querySelectorAll("li.pvs-list__item--line-separated"),
          );
        }
        if (listItems.length === 0) {
          listItems = Array.from(
            scope.querySelectorAll(".scaffold-finite-scroll__content li"),
          );
        }
        if (listItems.length === 0) {
          const mainUl = scope.querySelector("ul");
          if (mainUl) {
            listItems = Array.from(mainUl.querySelectorAll(":scope > li"));
          }
        }
        if (listItems.length === 0) {
          listItems = Array.from(
            scope.querySelectorAll(
              ".pvs-entity, [data-view-name*='profile-component-entity']",
            ),
          );
        }
        for (const item of listItems) {
          const role = item.getAttribute("role") || "";
          if (role.toLowerCase() === "tab") continue;
          if (item.querySelector('[role="tab"]')) continue;
          if (isPersonCard(item)) continue;
          const texts = extractItemLines(item);
          if (texts.length > 0) out.push(texts);
        }

        if (out.length > 0) return out;

        // Strategy D: "UUID componentkey" repeated siblings (new SDUI project UI).
        // Find a parent whose direct children are divs with UUID-like componentkey.
        const uuidRe = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
        const allContainers = Array.from(scope.querySelectorAll("div"));
        let bestParent: Element | null = null;
        let bestUuidChildren: Element[] = [];
        for (const p of allContainers) {
          if (p.closest('aside, [role="complementary"]')) continue;
          const uuidKids = Array.from(p.children).filter((c) => {
            const ck = c.getAttribute("componentkey") || "";
            return uuidRe.test(ck);
          });
          if (uuidKids.length > bestUuidChildren.length) {
            bestUuidChildren = uuidKids;
            bestParent = p;
          }
        }
        if (bestParent && bestUuidChildren.length >= 2) {
          for (const kid of bestUuidChildren) {
            if (isPersonCard(kid)) continue;
            const texts = extractItemLines(kid);
            if (texts.length > 0) out.push(texts);
          }
          if (out.length > 0) return out;
        }

        // Strategy E (last resort): all <p> in DOM order, split on date ranges
        const isDateLine = (t: string) =>
          /\b(19|20)\d{2}\b/.test(t) &&
          (/-|–|—|à|au|aujourd|pr[ée]sent|present|to\b/i.test(t));
        const allPs = Array.from(scope.querySelectorAll("p, h3, h4"))
          .filter((p) => !p.closest('aside, [role="complementary"]'))
          .filter((p) => !p.closest('[role="tab"], [role="tablist"]'))
          .map((p) => (p.textContent || "").replace(/\s+/g, " ").trim())
          .filter(Boolean);
        const cleanedPs = removeNoise(allPs);
        // Avoid person-card indicators
        if (!cleanedPs.some((t) => /·\s*(1er|2e|3e(\s*et\s*\+)?|1st|2nd|3rd(\+)?)/i.test(t))) {
          // Split into items when there is more than one date line
          const dateIdx: number[] = [];
          cleanedPs.forEach((t, i) => {
            if (isDateLine(t)) dateIdx.push(i);
          });
          if (dateIdx.length >= 1) {
            let start = 0;
            for (let k = 0; k < dateIdx.length; k++) {
              const next = dateIdx[k + 1];
              const end =
                next != null ? Math.max(start + 1, next - 2) : cleanedPs.length;
              const block = cleanedPs.slice(start, end);
              if (block.length > 0) out.push(block);
              start = end;
            }
          } else if (cleanedPs.length > 0) {
            // No dates at all → single item (e.g. skills list)
            for (const p of cleanedPs) out.push([p]);
          }
        }

        return out;
      };

      const raw = collectItems(document);

      // Post-processing: drop person-cards, split merged items with multiple date ranges
      const final: Array<string[]> = [];
      for (const entry of raw) {
        if (textsLookLikePerson(entry)) continue;
        const split = splitOnDateRanges(entry);
        for (const s of split) {
          if (s.length === 0) continue;
          if (textsLookLikePerson(s)) continue;
          final.push(s);
        }
      }
      return final;
    });
  } catch {
    return [];
  }
}

type SectionDetailLinks = {
  experience: string[];
  education: string[];
  volunteer: string[];
  projects: string[];
  skills: string[];
  languages: string[];
  certifications: string[];
};

async function discoverSectionDetailLinks(
  page: Page,
  profileUrl: string,
): Promise<SectionDetailLinks> {
  const empty: SectionDetailLinks = {
    experience: [],
    education: [],
    volunteer: [],
    projects: [],
    skills: [],
    languages: [],
    certifications: [],
  };

  try {
    const rows = await page.evaluate(() => {
      return Array.from(document.querySelectorAll("section")).map((section) => {
        const heading = (section.querySelector("h2")?.textContent || "").trim().toLowerCase();
        const hrefs = Array.from(section.querySelectorAll("a[href*='/details/']"))
          .map((a) => (a as HTMLAnchorElement).href)
          .filter(Boolean);
        return { heading, hrefs };
      });
    });

    const makeAbs = (href: string): string => {
      try {
        return new URL(href, profileUrl).toString();
      } catch {
        return href;
      }
    };

    const pushUnique = (arr: string[], href: string) => {
      const v = makeAbs(href);
      if (v && !arr.includes(v)) arr.push(v);
    };

    for (const row of rows) {
      for (const href of row.hrefs) {
        const h = row.heading;
        if (/exp[ée]rience|experience/.test(h)) pushUnique(empty.experience, href);
        if (/formation|education|[ée]tudes/.test(h)) pushUnique(empty.education, href);
        if (/b[ée]n[ée]volat|volunteer|volunteering|b[ée]n[ée]vole/.test(h)) pushUnique(empty.volunteer, href);
        if (/projets|projects/.test(h)) pushUnique(empty.projects, href);
        if (/comp[ée]tences|skills/.test(h)) pushUnique(empty.skills, href);
        if (/langues|languages/.test(h)) pushUnique(empty.languages, href);
        if (/certifications|licences|licenses/.test(h)) pushUnique(empty.certifications, href);
      }
    }

    return empty;
  } catch {
    return empty;
  }
}

async function scrapeDetailsPages(
  page: Page,
  profileUrl: string,
  detailPaths: string[],
  directUrls?: string[],
): Promise<Array<string[]>> {
  if (directUrls && directUrls.length > 0) {
    for (const absUrl of directUrls) {
      const items = await scrapeDetailsPageByUrl(page, absUrl);
      if (items.length > 0) return items;
    }
  }

  for (const path of detailPaths) {
    const items = await scrapeDetailsPage(page, profileUrl, path);
    if (items.length > 0) return items;
  }
  return [];
}

// ---- Extract skills directly from profile page (new SDUI UI) ----
async function extractProfileSkills(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const out: string[] = [];
    const seen = new Set<string>();
    // Each skill is wrapped in: div[componentkey^="com.linkedin.sdui.profile.skill("]
    // (but the SAME key is used for a "-divider" hr wrapper; skip those)
    const cards = Array.from(
      document.querySelectorAll(
        'div[componentkey^="com.linkedin.sdui.profile.skill("]',
      ),
    ).filter((el) => {
      const ck = el.getAttribute("componentkey") || "";
      return !ck.endsWith("-divider");
    });
    for (const card of cards) {
      // First <p> is the skill name; subsequent <p>s are endorsements context
      const p = card.querySelector("p");
      if (!p) continue;
      const name = (p.textContent || "").replace(/\s+/g, " ").trim();
      if (!name || name.length > 120) continue;
      if (seen.has(name)) continue;
      seen.add(name);
      out.push(name);
    }
    return out;
  });
}

// ---- Extract languages directly from profile page (new SDUI UI) ----
async function extractProfileLanguages(
  page: Page,
): Promise<Array<{ language: string; level: string }>> {
  return page.evaluate(() => {
    const out: Array<{ language: string; level: string }> = [];
    const seen = new Set<string>();
    // Find the Language section wrapper
    const wrapper = document.querySelector(
      'div[componentkey$="LanguageTopLevel"]',
    );
    if (!wrapper) return out;
    const section = wrapper.querySelector("section") || wrapper;
    // Each language is an entity-collection-item
    const items = Array.from(
      section.querySelectorAll(
        'div[componentkey^="entity-collection-item"]',
      ),
    );
    for (const it of items) {
      const ps = Array.from(it.querySelectorAll("p"))
        .map((p) => (p.textContent || "").replace(/\s+/g, " ").trim())
        .filter(Boolean);
      if (ps.length === 0) continue;
      const language = ps[0] || "";
      const level = ps[1] || "";
      if (!language || language.length > 60) continue;
      if (seen.has(language)) continue;
      seen.add(language);
      out.push({ language, level });
    }
    // Fallback: split on <hr> if no entity items were found
    if (out.length === 0) {
      const hr = section.querySelectorAll("hr");
      if (hr.length > 0) {
        const container = hr[0].parentElement;
        if (container) {
          const children = Array.from(container.children);
          let block: Element[] = [];
          const blocks: Element[][] = [];
          for (const ch of children) {
            if (ch.tagName === "HR") {
              if (block.length) {
                blocks.push(block);
                block = [];
              }
            } else if (ch.tagName !== "H2") {
              block.push(ch);
            }
          }
          if (block.length) blocks.push(block);
          for (const b of blocks) {
            const texts: string[] = [];
            for (const el of b) {
              el.querySelectorAll("p").forEach((p) => {
                const t = (p.textContent || "").replace(/\s+/g, " ").trim();
                if (t) texts.push(t);
              });
            }
            const language = texts[0] || "";
            const level = texts[1] || "";
            if (language && language.length < 60 && !seen.has(language)) {
              seen.add(language);
              out.push({ language, level });
            }
          }
        }
      }
    }
    return out;
  });
}

// ---- Main scraper ----

export async function scrapeLinkedInProfile(
  profileUrl: string,
  onProgress: (p: ScrapeProgress) => void,
  onMfaCodeRequested?: (ctx: MfaChallengeContext) => Promise<string>,
): Promise<ScrapeResult> {
  const email = process.env.LINKEDIN_EMAIL;
  const password = process.env.LINKEDIN_PASSWORD;

  if (!email || !password) {
    throw new Error(
      "Variables LINKEDIN_EMAIL et LINKEDIN_PASSWORD requises dans .env.local"
    );
  }

  const headless = process.env.LINKEDIN_HEADLESS !== "false";
  let browser: Browser | null = null;

  try {
    // ── 1. Launch browser ──
    onProgress({ step: "Lancement du navigateur...", percent: 5 });
    browser = await puppeteer.launch({
      headless,
      executablePath: CHROME_PATH,
      args: [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--window-size=1920,1080",
      ],
    });

    const page = await browser.newPage();
    await page.setUserAgent(randomUA());
    await page.setViewport({ width: 1920, height: 1080 });

    // Hide automation flags
    await page.evaluateOnNewDocument(() => {
      Object.defineProperty(navigator, "webdriver", { get: () => false });
      // @ts-expect-error — hide chrome driver
      window.chrome = { runtime: {} };
    });

    // ── 2. Login ──
    onProgress({ step: "Connexion à LinkedIn...", percent: 10 });
    await page.goto("https://www.linkedin.com/login", {
      waitUntil: "networkidle2",
      timeout: 30000,
    });
    await randomDelay(1000, 2000);

    // Dismiss cookie consent banner if present
    try {
      const cookieBtn = await page.$(
        'button[action-type="ACCEPT"], button.artdeco-global-alert__action, ' +
        'button[data-test-global-alert-action], button[data-control-name="ga-cookie.consent.accept.v4"]'
      );
      if (cookieBtn) await cookieBtn.click();
      await wait(500);
    } catch {}

    // Save debug screenshot of login page
    try {
      mkdirSync(join(process.cwd(), "debug"), { recursive: true });
      const buf = await page.screenshot({ fullPage: false });
      writeFileSync(join(process.cwd(), "debug", "00-login-page.png"), buf);
      const html = await page.content();
      saveDebug("00-login-page.html", html.slice(0, 50000));
    } catch {}

    // Find username field with multiple fallback selectors
    const usernameSelectors = [
      "#username",
      'input[name="session_key"]',
      'input[autocomplete="username"]',
      'input[type="email"]',
      'input[type="text"]',
    ];

    let usernameField = null;
    for (const sel of usernameSelectors) {
      try {
        usernameField = await page.waitForSelector(sel, { timeout: 5000 });
        if (usernameField) {
          onProgress({ step: `Champ login trouvé: ${sel}`, percent: 12 });
          break;
        }
      } catch {}
    }

    if (!usernameField) {
      // Save full HTML for debugging
      const html = await page.content();
      saveDebug("00-login-FAIL.html", html);
      throw new Error(
        "Impossible de trouver le champ de connexion LinkedIn. La page de login a peut-être changé. Voir debug/00-login-FAIL.html"
      );
    }

    await usernameField.type(email, { delay: 50 + Math.random() * 80 });
    await randomDelay(500, 1000);

    // Find password field
    const passwordSelectors = [
      "#password",
      'input[name="session_password"]',
      'input[autocomplete="current-password"]',
      'input[type="password"]',
    ];

    let passwordField = null;
    for (const sel of passwordSelectors) {
      try {
        passwordField = await page.waitForSelector(sel, { timeout: 5000 });
        if (passwordField) break;
      } catch {}
    }

    if (!passwordField) {
      throw new Error("Impossible de trouver le champ mot de passe LinkedIn.");
    }

    await passwordField.type(password, { delay: 50 + Math.random() * 80 });
    await randomDelay(500, 1000);

    // Find and click submit button
    const submitSelectors = [
      'button[type="submit"]',
      'button[data-litms-control-urn="login-submit"]',
      'button.btn__primary--large',
      'button[aria-label="S\'identifier"]',
      'button[aria-label="Sign in"]',
    ];

    let submitBtn = null;
    for (const sel of submitSelectors) {
      try {
        submitBtn = await page.$(sel);
        if (submitBtn) break;
      } catch {}
    }

    if (!submitBtn) {
      throw new Error("Impossible de trouver le bouton de connexion LinkedIn.");
    }

    await Promise.all([
      submitBtn.click(),
      page.waitForNavigation({ waitUntil: "networkidle2", timeout: 30000 }),
    ]);

    const mfaInputSelectors = [
      'input[name="pin"]',
      'input[name="verification_pin"]',
      'input[autocomplete="one-time-code"]',
      'input[inputmode="numeric"]',
      'input[id*="pin"]',
      'input[type="tel"]',
    ];

    const isMfaStep = await page.evaluate(() => {
      const fullText = document.body?.innerText?.toLowerCase() || "";
      const hints = [
        "enter the code",
        "verification code",
        "security verification",
        "check your email",
        "saisissez le code",
        "code de vérification",
        "vérification de sécurité",
      ];
      const hasInput = !!document.querySelector(
        'input[name="pin"], input[name="verification_pin"], input[autocomplete="one-time-code"], input[inputmode="numeric"], input[id*="pin"], input[type="tel"]'
      );
      return hasInput || hints.some((h) => fullText.includes(h));
    });

    if (isMfaStep || page.url().includes("checkpoint") || page.url().includes("challenge")) {
      if (!onMfaCodeRequested) {
        throw new Error(
          "LinkedIn demande un code de vérification, mais aucun flux de saisie de code n'est configuré."
        );
      }

      onProgress({
        step: "Code de vérification requis: attente de votre saisie...",
        percent: 16,
      });

      let mfaInput = null;
      for (const sel of mfaInputSelectors) {
        try {
          mfaInput = await page.waitForSelector(sel, { timeout: 2000 });
          if (mfaInput) break;
        } catch {}
      }

      if (!mfaInput) {
        throw new Error(
          "LinkedIn demande une vérification mais le champ de code est introuvable."
        );
      }

      const code = (await onMfaCodeRequested({
        reason: "LinkedIn a demandé un code de vérification envoyé par e-mail.",
        url: page.url(),
      }))
        .trim();

      if (!code) {
        throw new Error("Aucun code MFA fourni.");
      }

      await mfaInput.click({ clickCount: 3 }).catch(() => {});
      await mfaInput.type(code, { delay: 60 + Math.random() * 50 });
      await randomDelay(400, 800);

      const mfaSubmitSelectors = [
        'button[type="submit"]',
        'button[id*="verify"]',
        'button[aria-label*="Verify"]',
        'button[aria-label*="Vérifier"]',
      ];

      let mfaSubmit = null;
      for (const sel of mfaSubmitSelectors) {
        mfaSubmit = await page.$(sel);
        if (mfaSubmit) break;
      }

      if (!mfaSubmit) {
        throw new Error("Bouton de validation du code introuvable.");
      }

      await Promise.all([
        mfaSubmit.click(),
        page.waitForNavigation({ waitUntil: "networkidle2", timeout: 30000 }).catch(() => {}),
      ]);

      onProgress({ step: "Code vérifié, reprise du scraping...", percent: 18 });
    }

    // Check for security challenge or failed login
    const postLoginUrl = page.url();
    if (postLoginUrl.includes("login")) {
      throw new Error(
        "Échec de la connexion LinkedIn. Vérifiez vos identifiants dans .env.local"
      );
    }

    onProgress({ step: "Connecté à LinkedIn ✓", percent: 18 });
    await randomDelay(2000, 3000);

    // Save debug screenshot after login
    try {
      const loginScreenshot = await page.screenshot({ encoding: "base64" });
      saveDebug("01-after-login.txt", `URL: ${postLoginUrl}\nScreenshot saved as base64`);
    } catch {}

    // ── 3. Navigate to profile ──
    onProgress({ step: "Navigation vers le profil...", percent: 22 });
    await page.goto(profileUrl, { waitUntil: "networkidle2", timeout: 30000 });

    // Wait for the page to have meaningful content
    await page
      .waitForSelector("h1", { timeout: 15000 })
      .catch(() => {});
    await randomDelay(2000, 3000);

    // Check we're on the profile page
    const profilePageUrl = page.url();
    if (
      profilePageUrl.includes("authwall") ||
      profilePageUrl.includes("login")
    ) {
      throw new Error(
        "Session LinkedIn expirée ou profil inaccessible. Réessayez."
      );
    }

    // ── 4. Scroll to load all lazy sections ──
    onProgress({ step: "Chargement du profil complet...", percent: 26 });
    await autoScroll(page);
    await randomDelay(1000, 1500);

    // Second scroll pass (some content loads after first scroll)
    await autoScroll(page);
    await randomDelay(500, 1000);

    // Expand all "see more" buttons
    await clickAllSeeMore(page);

    // ── 5. Debug: discover page structure ──
    const pageDebug = await page.evaluate(() => {
      const h1 = document.querySelector("h1")?.textContent?.trim() || "";
      const pageTitle = document.title;
      const sectionsInfo = Array.from(document.querySelectorAll("section")).map(
        (s) => {
          const idEls = s.querySelectorAll("[id]");
          const ids = Array.from(idEls)
            .map((el) => el.id)
            .filter(Boolean);
          const h2 = s.querySelector("h2")?.textContent?.trim() || "";
          const liCount = s.querySelectorAll("li").length;
          return { ids, h2, liCount };
        },
      );
      return { h1, pageTitle, url: location.href, sectionsInfo };
    });

    // Save debug info
    saveDebug(
      "02-profile-structure.json",
      JSON.stringify(pageDebug, null, 2),
    );

    // Save screenshot
    try {
      const buf = await page.screenshot({ fullPage: false });
      writeFileSync(join(process.cwd(), "debug", "02-profile.png"), buf);
    } catch {}

    onProgress({
      step: pageDebug.h1
        ? `Profil: "${pageDebug.h1}" (${pageDebug.sectionsInfo.length} sections)`
        : `⚠ Nom non trouvé sur la page (${pageDebug.sectionsInfo.length} sections)`,
      percent: 30,
    });

    if (!pageDebug.h1) {
      // Save full HTML for debugging
      const html = await page.content();
      saveDebug("02-profile-FULL.html", html);
    }

    // Discover exact section details links from "Voir tout" anchors
    const sectionDetailLinks = await discoverSectionDetailLinks(page, profileUrl);
    saveDebug("02-section-detail-links.json", JSON.stringify(sectionDetailLinks, null, 2));

    // ── 6. Personal info ──
    onProgress({ step: "Extraction des informations personnelles...", percent: 33 });

    const personalInfo = await page.evaluate((url: string) => {
      // ── Name from h1 ──
      const h1 = document.querySelector("h1");
      let fullName = h1?.textContent?.trim() || "";

      // Fallback 1: page title "Firstname Lastname | LinkedIn"
      if (!fullName) {
        const titleName = document.title.split("|")[0]?.trim() || "";
        if (titleName && titleName.toLowerCase() !== "linkedin") {
          fullName = titleName;
        }
      }

      // Fallback 2: first non-generic heading from profile hero card
      if (!fullName) {
        const headingCandidates = Array.from(
          document.querySelectorAll("main h1, main h2, section h2")
        )
          .map((el) => el.textContent?.trim() || "")
          .filter(Boolean)
          .filter((t) => !/notification|activité|infos|expérience|formation|projets|compétences/i.test(t));
        fullName = headingCandidates.find((t) => t.split(/\s+/).length >= 2) || "";
      }

      const nameParts = fullName.split(/\s+/);
      const firstName = nameParts[0] || "";
      const lastName = nameParts.slice(1).join(" ") || "";

      // ── Headline / title ──
      let title = "";

      // Strategy A: CSS class selectors (stable on most LinkedIn versions)
      const headlineSelectors = [
        ".text-body-medium.break-words",
        ".text-body-medium",
        'div[data-generated-suggestion-target="urn:li:fsu_profileActionDelegate"]',
      ];
      for (const sel of headlineSelectors) {
        const el = document.querySelector(sel);
        const text = el?.textContent?.trim() || "";
        if (text && text !== fullName && text.length > 2 && text.length < 300) {
          title = text;
          break;
        }
      }

      // Strategy C: from the hero section that contains the profile name heading
      if (!title && fullName) {
        const heroSection = Array.from(document.querySelectorAll("section")).find((s) => {
          const h2 = s.querySelector("h2")?.textContent?.trim() || "";
          return h2.toLowerCase() === fullName.toLowerCase();
        });

        if (heroSection) {
          const lines = (heroSection.textContent || "")
            .split("\n")
            .map((s) => s.trim())
            .filter(Boolean)
            .filter((s) => s !== fullName)
            .filter((s) => s.length > 2 && s.length < 180)
            .filter((s) => !/relation|follower|abonné|contact/i.test(s));
          title = lines[0] || "";
        }
      }

      // Strategy B: DOM traversal from h1 — find the next text element
      if (!title && h1) {
        // Walk up from h1 to find a container, then look at siblings
        let container = h1.parentElement;
        for (let depth = 0; depth < 5 && container; depth++) {
          const sibling = container.nextElementSibling;
          if (sibling) {
            const text = sibling.textContent?.trim() || "";
            // Headline is typically short (job title)
            if (text && text.length > 3 && text.length < 200 && text !== fullName) {
              title = text;
              break;
            }
          }
          container = container.parentElement;
        }
      }

      // ── Location / City ──
      let city = "";

      // Strategy A: CSS class selectors
      const locationSelectors = [
        ".text-body-small.inline.t-black--light.break-words",
        ".pv-text-details__left-panel .text-body-small",
        "span.text-body-small.inline",
        ".text-body-small.break-words",
      ];
      for (const sel of locationSelectors) {
        const els = document.querySelectorAll(sel);
        for (const el of els) {
          const text = el.textContent?.trim() || "";
          // Location text is typically short and doesn't contain "relations" / "followers"
          if (
            text &&
            text.length > 2 &&
            text.length < 100 &&
            !text.includes("relation") &&
            !text.includes("follower") &&
            !text.includes("abonné") &&
            text !== fullName &&
            text !== title
          ) {
            city = text.split(",")[0]?.trim() || text;
            break;
          }
        }
        if (city) break;
      }

      // Strategy B: city from hero card lines
      if (!city && fullName) {
        const heroSection = Array.from(document.querySelectorAll("section")).find((s) => {
          const h2 = s.querySelector("h2")?.textContent?.trim() || "";
          return h2.toLowerCase() === fullName.toLowerCase();
        });

        if (heroSection) {
          const lines = (heroSection.textContent || "")
            .split("\n")
            .map((s) => s.trim())
            .filter(Boolean)
            .filter((s) => s !== fullName)
            .filter((s) => !/relation|follower|abonné|contact/i.test(s));
          const cityLine = lines.find((s) => s.includes(",") || /france|paris|lyon|marseille|toulouse/i.test(s));
          if (cityLine) {
            city = cityLine.split(",")[0]?.trim() || cityLine;
          }
        }
      }

      // ── Summary from #about section ──
      let summary = "";

      // Strategy A: find #about anchor
      const aboutAnchor = document.querySelector("#about");
      let aboutSection: Element | null = null;

      if (aboutAnchor) {
        aboutSection = aboutAnchor.closest("section");
      }

      // Strategy B: find by heading text
      if (!aboutSection) {
        const allSections = document.querySelectorAll("section");
        for (const s of allSections) {
          const h2Text =
            s.querySelector("h2")?.textContent?.trim()?.toLowerCase() || "";
          if (
            h2Text.includes("propos") ||
            h2Text === "about" ||
            h2Text.includes("about")
          ) {
            aboutSection = s;
            break;
          }
        }
      }

      if (aboutSection) {
        // Try 1: inline-show-more-text
        const showMore = aboutSection.querySelector(
          ".inline-show-more-text, .pv-shared-text-with-see-more"
        );
        if (showMore) {
          const spans = showMore.querySelectorAll(
            'span[aria-hidden="true"]'
          );
          if (spans.length > 0) {
            summary = Array.from(spans)
              .map((s) => s.textContent?.trim())
              .filter(Boolean)
              .join("\n");
          } else {
            // Sometimes the text is directly in the container
            summary = showMore.textContent?.trim() || "";
          }
        }

        // Try 2: all aria-hidden spans in section (skip the heading)
        if (!summary) {
          const spans = aboutSection.querySelectorAll(
            'span[aria-hidden="true"]'
          );
          const texts = Array.from(spans)
            .map((s) => s.textContent?.trim() || "")
            .filter(
              (t) =>
                t.length > 20 &&
                t !== "À propos" &&
                t !== "About" &&
                t !== "Infos",
            );
          summary = texts.join("\n");
        }

        // Try 3: [data-testid="expandable-text-box"] content (new SDUI about box)
        if (!summary) {
          const expBox = aboutSection.querySelector(
            '[data-testid="expandable-text-box"]',
          );
          if (expBox) {
            summary = (expBox.textContent || "").trim();
          }
        }

        // Try 4: <p> tags in the section concatenated
        if (!summary) {
          const ps = Array.from(aboutSection.querySelectorAll("p"))
            .map((p) => (p.textContent || "").trim())
            .filter((t) => t.length > 20);
          if (ps.length > 0) summary = ps.join("\n");
        }

        // Try 5: any div with substantial text in the section
        if (!summary) {
          const allDivs = aboutSection.querySelectorAll("div");
          for (const d of allDivs) {
            const t = d.textContent?.trim() || "";
            if (
              t.length > 50 &&
              t !== aboutSection.textContent?.trim()
            ) {
              summary = t;
              break;
            }
          }
        }
      }

      // Final fallback: "Infos" section text when About is empty
      if (!summary) {
        const infoSection = Array.from(document.querySelectorAll("section")).find((s) => {
          const h2 = s.querySelector("h2")?.textContent?.trim()?.toLowerCase() || "";
          return h2.includes("infos") || h2.includes("about") || h2.includes("propos");
        });
        if (infoSection) {
          const full = (infoSection.textContent || "")
            .split("\n")
            .map((s) => s.trim())
            .filter(Boolean)
            .filter((s) => !/^infos$|^about$|^à propos$/i.test(s))
            .join("\n");
          if (full.length > 20) summary = full;
        }
      }

      // Strip leading section label like "Infos", "À propos", "About"
      // and trailing "… plus" suffix. Run LAST so it applies to all strategies.
      if (summary) {
        summary = summary
          .replace(/^\s*(infos?|à\s*propos|a\s*propos|about)\s*[:\-–—]?\s*/i, "")
          .replace(/\s*…\s*plus\s*$/i, "")
          .replace(/\s*\.\.\.\s*plus\s*$/i, "")
          .trim();
      }

      return {
        firstName,
        lastName,
        email: "",
        phone: "",
        title,
        city,
        postalCode: "",
        linkedIn: url,
        website: "",
        summary,
        address: "",
      };
    }, profileUrl);

    onProgress({
      step: personalInfo.firstName
        ? `${personalInfo.firstName} ${personalInfo.lastName} — "${personalInfo.title.slice(0, 40)}…"`
        : "⚠ Nom non trouvé — vérifiez la connexion",
      percent: 38,
    });

    // Save personal info debug
    saveDebug(
      "03-personal-info.json",
      JSON.stringify(personalInfo, null, 2),
    );

    await randomDelay(500, 1000);

    // ══════════════════════════════════════════════════════════
    // PHASE 2: Extract sections from the profile page
    // (we already have the page loaded and scrolled)
    // ══════════════════════════════════════════════════════════

    // ── 7. Experience ──
    onProgress({ step: "Extraction des expériences...", percent: 40 });

    let expItems = await findAndExtractSection(
      page,
      ["experience"],
      ["Expérience", "Experience"],
      SECTION_COMPONENT_KEYS.experience,
    );

    // If profile section is empty, try the /details/ page
    if (expItems.length === 0) {
      onProgress({ step: "Expériences: tentative page détails...", percent: 42 });
      expItems = await scrapeDetailsPages(
        page,
        profileUrl,
        ["experience", "experiences"],
        sectionDetailLinks.experience,
      );
    }

    saveDebug("04-experience-raw.json", JSON.stringify(expItems, null, 2));

    const parsedExperience = expItems.map((texts) => {
      const parsed = parseExperienceEntry(texts);
      return {
        id: genId(),
        title: parsed.title,
        company: parsed.company,
        startDate: parsed.startDate,
        endDate: parsed.endDate,
        current: parsed.current,
        description: parsed.description,
        location: parsed.location,
      };
    }).filter((e) => e.title || e.company);

    onProgress({
      step: `${parsedExperience.length} expérience(s) ✓`,
      percent: 48,
    });
    await randomDelay(500, 1000);

    // ── 8. Education ──
    onProgress({ step: "Extraction des formations...", percent: 50 });

    // Navigate back to profile for remaining sections
    if (expItems.length === 0 || page.url() !== profileUrl) {
      await page.goto(profileUrl, { waitUntil: "networkidle2", timeout: 20000 });
      await page.waitForSelector("h1", { timeout: 10000 }).catch(() => {});
      await autoScroll(page);
      await clickAllSeeMore(page);
    }

    let eduItems = await findAndExtractSection(
      page,
      ["education"],
      ["Formation", "Education", "Études"],
      SECTION_COMPONENT_KEYS.education,
    );

    // Always prefer the /details/ page when available — it's the complete list.
    if (sectionDetailLinks.education.length > 0) {
      onProgress({ step: "Formations: page détails...", percent: 52 });
      const detailsEdu = await scrapeDetailsPages(
        page,
        profileUrl,
        ["education", "educations"],
        sectionDetailLinks.education,
      );
      if (detailsEdu.length > eduItems.length) {
        eduItems = detailsEdu;
      }
    } else if (eduItems.length === 0) {
      eduItems = await scrapeDetailsPages(
        page,
        profileUrl,
        ["education", "educations"],
        sectionDetailLinks.education,
      );
    }

    saveDebug("05-education-raw.json", JSON.stringify(eduItems, null, 2));

    const parsedEducation = eduItems.map((texts) => {
      const school = texts[0] || "";
      const degreeField = texts[1] || "";
      const degreeParts = degreeField.split(",").map((s) => s.trim());
      const degree = degreeParts[0] || "";
      const field = degreeParts.slice(1).join(", ") || "";

      // Find date string
      let dateRaw = "";
      for (let i = 2; i < Math.min(texts.length, 5); i++) {
        if (/\d{4}/.test(texts[i])) {
          dateRaw = texts[i];
          break;
        }
      }
      if (!dateRaw) dateRaw = texts[2] || "";

      const { start, end, current } = parseDateRangeFromAnyText(dateRaw || texts.join(" "));
      const descParts = texts.slice(3).filter((s) => s.length > 15);

      return {
        id: genId(),
        school,
        degree,
        field,
        startDate: start,
        endDate: end,
        current,
        description: descParts.join("\n"),
        location: "",
      };
    });

    onProgress({
      step: `${parsedEducation.length} formation(s) ✓`,
      percent: 56,
    });
    await randomDelay(500, 1000);

    // ── 9. Volunteer ──
    onProgress({ step: "Extraction du bénévolat...", percent: 58 });

    // Make sure we're on the profile page
    if (!page.url().includes("/in/")) {
      await page.goto(profileUrl, { waitUntil: "networkidle2", timeout: 20000 });
      await page.waitForSelector("h1", { timeout: 10000 }).catch(() => {});
      await autoScroll(page);
    }

    let volunteerItems = await findAndExtractSection(
      page,
      ["volunteering_experience", "volunteer_experience", "volunteering"],
      ["Bénévolat", "Volunteer", "Volunteering", "bénévole"],
      SECTION_COMPONENT_KEYS.volunteer,
    );

    // Always prefer the /details/ page when available
    if (sectionDetailLinks.volunteer.length > 0) {
      onProgress({ step: "Bénévolat: page détails...", percent: 60 });
      const detailsVol = await scrapeDetailsPages(page, profileUrl, [
        "volunteering-experiences",
        "volunteering-experience",
        "volunteering",
      ], sectionDetailLinks.volunteer);
      if (detailsVol.length > volunteerItems.length) {
        volunteerItems = detailsVol;
      }
    } else if (volunteerItems.length === 0) {
      volunteerItems = await scrapeDetailsPages(page, profileUrl, [
        "volunteering-experiences",
        "volunteering-experience",
        "volunteering",
      ], sectionDetailLinks.volunteer);
    }

    saveDebug("06-volunteer-raw.json", JSON.stringify(volunteerItems, null, 2));

    const parsedVolunteer = volunteerItems.map((texts) => {
      const role = texts[0] || "";
      const organization = texts[1] || "";
      let dateRaw = "";
      for (let i = 2; i < Math.min(texts.length, 5); i++) {
        if (/\d{4}/.test(texts[i]) || /présent|present/i.test(texts[i])) {
          dateRaw = texts[i];
          break;
        }
      }
      if (!dateRaw) dateRaw = texts[2] || "";
      const { start, end, current } = parseDateRangeFromAnyText(dateRaw || texts.join(" "));
      const descParts = texts
        .slice(3)
        .filter(
          (s) =>
            s.length > 10 &&
            !/\.(png|jpg|jpeg|gif|webp|svg|pdf|docx?|pptx?)\b/i.test(s) &&
            !/@\w+\)\s*(•|·|-)\s*instagram/i.test(s),
        )
        .map((s) => s.replace(/…\s*plus\s*$/i, "").trim())
        .filter(Boolean);

      return {
        id: genId(),
        organization,
        role,
        startDate: start,
        endDate: end,
        current,
        description: descParts.join("\n"),
      };
    }).filter((v) => v.role || v.organization);

    onProgress({
      step: `${parsedVolunteer.length} bénévolat ✓`,
      percent: 63,
    });
    await randomDelay(500, 1000);

    // ── 10. Projects ──
    onProgress({ step: "Extraction des projets...", percent: 65 });

    let projectItems = await findAndExtractSection(
      page,
      ["projects"],
      ["Projets", "Projects"],
      SECTION_COMPONENT_KEYS.projects,
    );

    if (projectItems.length === 0) {
      projectItems = await scrapeDetailsPages(
        page,
        profileUrl,
        ["projects", "project"],
        sectionDetailLinks.projects,
      );
    }

    saveDebug("07-projects-raw.json", JSON.stringify(projectItems, null, 2));

    const parsedProjects = projectItems.map((texts) => {
      const name = texts[0] || "";
      let dateRaw = "";
      for (let i = 1; i < Math.min(texts.length, 4); i++) {
        if (/\d{4}/.test(texts[i])) {
          dateRaw = texts[i];
          break;
        }
      }
      if (!dateRaw) dateRaw = texts[1] || "";
      const { start, end, current } = parseDateRangeFromAnyText(dateRaw || texts.join(" "));

      // Extract technologies from skill-summary line and clean description
      let technologies = "";
      const descParts = texts
        .slice(2)
        .filter((s) => {
          if (s.length <= 10) return false;
          // Image/document filenames are not description text
          if (/\.(png|jpg|jpeg|gif|webp|svg|pdf|docx?|pptx?)\b/i.test(s)) return false;
          // Skill summary line: "X, Y et N compétences de plus" -> capture as technologies
          if (/\bet\s+\d+\s+comp[ée]tences?\s+de\s+plus\b/i.test(s) ||
              /\band\s+\d+\s+more\s+skills?\b/i.test(s)) {
            technologies = s
              .replace(/\s*(et|and)\s+\d+\s+(comp[ée]tences?|more\s+skills?).*$/i, "")
              .replace(/\s*…\s*plus\s*$/i, "")
              .trim();
            return false;
          }
          // "Associé(e) à <school>" is association metadata, not description
          if (/^associ[ée]\(e\)\s+à\s+/i.test(s)) return false;
          return true;
        })
        .map((s) =>
          s
            .replace(/…\s*plus\s*$/i, "")
            .replace(/\s+…\s*$/, "")
            .trim(),
        )
        .filter(Boolean);

      return {
        id: genId(),
        name,
        description: descParts.join("\n"),
        technologies,
        url: "",
        startDate: start,
        endDate: end,
        current,
      };
    });

    onProgress({
      step: `${parsedProjects.length} projet(s) ✓`,
      percent: 70,
    });
    await randomDelay(500, 1000);

    // ══════════════════════════════════════════════════════════
    // PHASE 3: Navigate to /details/ pages for skills, languages, certs
    // ══════════════════════════════════════════════════════════

    // ── 11. Skills ──
    onProgress({ step: "Extraction des compétences...", percent: 74 });

    // Ensure we're on the profile page
    if (!page.url().includes("/in/") || page.url().includes("/details/")) {
      await page.goto(profileUrl, { waitUntil: "networkidle2", timeout: 20000 });
      await page.waitForSelector("h1", { timeout: 10000 }).catch(() => {});
      await autoScroll(page);
      await clickAllSeeMore(page);
    }

    // Strategy 1: dedicated profile skills extractor (new SDUI UI leaf keys)
    let skills = await extractProfileSkills(page);
    let skillItems: Array<string[]> = skills.map((s) => [s]);

    // Strategy 2: /details/skills/ page for the COMPLETE list (supplement profile)
    if (sectionDetailLinks.skills.length > 0) {
      const detailsSkills = await scrapeDetailsPages(
        page,
        profileUrl,
        [],
        sectionDetailLinks.skills,
      );
      // Validate: must have more than one item AND not just tab labels
      const looksValid =
        detailsSkills.length >= 2 ||
        (detailsSkills.length === 1 &&
          !/^(langues|languages|comp[ée]tences|skills)$/i.test(
            detailsSkills[0][0] || "",
          ));
      if (looksValid && detailsSkills.length > skillItems.length) {
        skillItems = detailsSkills;
        skills = []; // re-parse from skillItems below
      }
    }

    // Strategy 3: generic section extractor on profile
    if (skills.length === 0 && skillItems.length === 0) {
      if (!page.url().includes("/in/") || page.url().includes("/details/")) {
        await page.goto(profileUrl, { waitUntil: "networkidle2", timeout: 20000 });
        await page.waitForSelector("h1", { timeout: 10000 }).catch(() => {});
        await autoScroll(page);
      }
      skillItems = await findAndExtractSection(
        page,
        ["skills"],
        ["Compétences", "Skills"],
        SECTION_COMPONENT_KEYS.skills,
      );
    }

    saveDebug("08-skills-raw.json", JSON.stringify(skillItems, null, 2));

    if (skills.length === 0) {
      const seenSkills = new Set<string>();
      for (const texts of skillItems) {
        const skillName = texts[0];
        if (
          skillName &&
          skillName.length < 60 &&
          !seenSkills.has(skillName) &&
          !/^\d/.test(skillName) &&
          !skillName.includes(" - ") &&
          !/endorsement|recommand/i.test(skillName) &&
          !/^(tout|all|connaissances du secteur|outils et technologie|comp[ée]tences interpersonnelles|langues)$/i.test(skillName) &&
          !/·\s*(1er|2e|3e|1st|2nd|3rd)/i.test(skillName)
        ) {
          seenSkills.add(skillName);
          skills.push(skillName);
        }
      }
    }

    onProgress({ step: `${skills.length} compétence(s) ✓`, percent: 82 });
    await randomDelay(500, 1000);

    // ── 12. Languages ──
    onProgress({ step: "Extraction des langues...", percent: 84 });

    // Ensure we're on the profile page
    if (!page.url().includes("/in/") || page.url().includes("/details/")) {
      await page.goto(profileUrl, { waitUntil: "networkidle2", timeout: 20000 });
      await page.waitForSelector("h1", { timeout: 10000 }).catch(() => {});
      await autoScroll(page);
      await clickAllSeeMore(page);
    }

    // Strategy 1: dedicated profile languages extractor
    let languagesList = await extractProfileLanguages(page);
    let langItems: Array<string[]> = languagesList.map((l) =>
      l.level ? [l.language, l.level] : [l.language],
    );

    // Strategy 2: /details/languages/ page when link exists (complete list)
    if (languagesList.length === 0 && sectionDetailLinks.languages.length > 0) {
      langItems = await scrapeDetailsPages(
        page,
        profileUrl,
        [],
        sectionDetailLinks.languages,
      );
    }

    // Strategy 3: generic section extractor on profile
    if (langItems.length === 0) {
      if (!page.url().includes("/in/") || page.url().includes("/details/")) {
        await page.goto(profileUrl, { waitUntil: "networkidle2", timeout: 20000 });
        await page.waitForSelector("h1", { timeout: 10000 }).catch(() => {});
        await autoScroll(page);
      }
      langItems = await findAndExtractSection(
        page,
        ["languages"],
        ["Langues", "Languages"],
        SECTION_COMPONENT_KEYS.languages,
      );
    }

    saveDebug("09-languages-raw.json", JSON.stringify(langItems, null, 2));

    const languages = languagesList.length > 0
      ? languagesList.map((l) => ({
          id: genId(),
          language: l.language,
          level: l.level,
        }))
      : langItems
          .map((texts) => ({
            id: genId(),
            language: texts[0] || "",
            level: texts[1] || "",
          }))
          .filter(
            (l) =>
              l.language &&
              l.language.length < 50 &&
              !/·\s*(1er|2e|3e|1st|2nd|3rd)/i.test(l.language) &&
              !/·\s*(1er|2e|3e|1st|2nd|3rd)/i.test(l.level),
          );

    onProgress({ step: `${languages.length} langue(s) ✓`, percent: 90 });
    await randomDelay(500, 1000);

    // ── 13. Certifications ──
    onProgress({ step: "Extraction des certifications...", percent: 92 });

    let certItems = await scrapeDetailsPages(page, profileUrl, [
      "licenses-and-certifications",
      "certifications",
      "licenses",
    ], sectionDetailLinks.certifications);

    if (certItems.length === 0) {
      if (!page.url().includes("/in/")) {
        await page.goto(profileUrl, { waitUntil: "networkidle2", timeout: 20000 });
        await page.waitForSelector("h1", { timeout: 10000 }).catch(() => {});
        await autoScroll(page);
      }
      certItems = await findAndExtractSection(
        page,
        ["licenses_and_certifications", "certifications"],
        ["Licences et certifications", "Certifications", "Licenses"],
        SECTION_COMPONENT_KEYS.certifications,
      );
    }

    saveDebug("10-certifications-raw.json", JSON.stringify(certItems, null, 2));

    const certifications = certItems
      .map((texts) => {
        const name = texts[0] || "";
        let issuer = "";
        let issueDateRaw = "";
        for (let i = 1; i < texts.length; i++) {
          const t = texts[i];
          if (!t) continue;
          // Format "Issuer · Emis le avr. 2024" or "Issuer · Issued Apr 2024"
          if (/\s·\s/.test(t) && /emis|issued|d[ée]livr/i.test(t)) {
            const parts = t.split(/\s+·\s+/);
            if (!issuer) issuer = (parts[0] || "").trim();
            const rest = parts.slice(1).join(" · ");
            issueDateRaw = rest.replace(/^(emis le|issued|d[ée]livr[ée]\s*(le)?)\s*/i, "").trim();
            break;
          }
          if (!issuer && t.length < 120 && !/identifiant|credential/i.test(t) && !/\d{4}/.test(t)) {
            issuer = t;
          }
          if (!issueDateRaw && /emis|issued|d[ée]livr/i.test(t)) {
            issueDateRaw = t.replace(/.*(emis le|issued|d[ée]livr[ée]\s*(le)?)\s*/i, "").trim();
          }
        }
        const fromHint = issueDateRaw ? parseLinkedInDate(issueDateRaw) : "";
        const fromAll = parseDateRangeFromAnyText(texts.join(" ")).start;
        return {
          id: genId(),
          name,
          issuer,
          date: fromHint || fromAll || "",
          url: "",
        };
      })
      .filter((c) => c.name && c.name.length < 140);

    onProgress({ step: `${certifications.length} certification(s) ✓`, percent: 97 });

    // ── Done ──
    const result: ScrapeResult = {
      personalInfo,
      education: parsedEducation,
      experience: parsedExperience,
      volunteer: parsedVolunteer,
      projects: parsedProjects,
      skills,
      languages,
      certifications,
    };

    saveDebug("11-final-result.json", JSON.stringify(result, null, 2));
    onProgress({ step: "Import terminé ✓", percent: 100 });

    return result;
  } finally {
    if (browser) {
      await browser.close().catch(() => {});
    }
  }
}
