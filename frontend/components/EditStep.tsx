"use client";

import { ArrowDown, ArrowUp, Pencil, Plus, Sparkles, Trash, User } from "lucide-react";
import { useState, type ReactNode } from "react";
import { SECTIONS, SECTION_LABELS, SECTION_STYLE, newItem, type FieldDef } from "@/lib/sections";
import { useStore } from "@/lib/store";
import { ALL_SECTIONS, type Basics, type CV, type Item, type ListKey, type SectionKey } from "@/lib/types";
import { TargetCard } from "./TargetCard";
import { Button, Card, Field, IconTile, Input, Textarea } from "./ui";

/* ------------------------------------------------------------------ state helpers */

function useCvActions() {
  const { cv, update } = useStore();
  const setItems = (key: ListKey, fn: (items: Item[]) => Item[]) =>
    update((c) => ({ ...c, profile: { ...c.profile, [key]: fn(c.profile[key]) } }));
  const setBasics = (patch: Partial<Basics>) =>
    update((c) => ({ ...c, profile: { ...c.profile, basics: { ...c.profile.basics, ...patch } } }));
  const setSections = (fn: (s: SectionKey[]) => SectionKey[]) =>
    update((c): CV => ({ ...c, settings: { ...c.settings, sections: fn(c.settings.sections) } }));
  return { cv, setItems, setBasics, setSections };
}

function move<T>(arr: T[], index: number, dir: -1 | 1): T[] {
  const j = index + dir;
  if (j < 0 || j >= arr.length) return arr;
  const out = [...arr];
  [out[index], out[j]] = [out[j], out[index]];
  return out;
}

/* ------------------------------------------------------------------ fields */

function TagsInput({ value, onChange, ...rest }: { value: string[]; onChange: (v: string[]) => void; placeholder?: string }) {
  const [draft, setDraft] = useState<string | null>(null);
  return (
    <Input
      {...rest}
      value={draft ?? value.join(", ")}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => {
        if (draft === null) return;
        onChange(draft.split(",").map((s) => s.trim()).filter(Boolean));
        setDraft(null);
      }}
    />
  );
}

function ItemFields({ item, fields, onChange }: { item: Item; fields: FieldDef[]; onChange: (patch: Partial<Item>) => void }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {fields.map((f) => {
        const v = item[f.key];
        if (f.type === "bool")
          return (
            <label key={f.key} className="flex items-center gap-2 self-end pb-2 text-sm">
              <input type="checkbox" className="accent-brand" checked={Boolean(v)} onChange={(e) => onChange({ [f.key]: e.target.checked })} />
              {f.label}
            </label>
          );
        return (
          <Field key={f.key} label={f.label} className={f.wide ? "sm:col-span-2" : ""}>
            {f.type === "textarea" ? (
              <Textarea value={String(v ?? "")} onChange={(e) => onChange({ [f.key]: e.target.value })} />
            ) : f.type === "tags" ? (
              <TagsInput value={Array.isArray(v) ? v : []} onChange={(tags) => onChange({ [f.key]: tags })} />
            ) : (
              <Input value={String(v ?? "")} placeholder={f.placeholder} onChange={(e) => onChange({ [f.key]: e.target.value })} />
            )}
          </Field>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ section shell */

function SectionShell({ sectionKey, count, children, actions }: { sectionKey: SectionKey; count?: string; children: ReactNode; actions?: ReactNode }) {
  const { cv, setSections } = useCvActions();
  const order = cv.settings.sections;
  const index = order.indexOf(sectionKey);
  const enabled = index >= 0;

  const { color, Icon } = SECTION_STYLE[sectionKey];

  return (
    <section
      className={`overflow-hidden rounded-lg border bg-white ${enabled ? "border-line" : "border-dashed border-line/80 bg-white/60"}`}
      style={enabled ? { borderTopColor: color, borderTopWidth: 3 } : undefined}
    >
      <header className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-line/70 px-4 py-3">
        <IconTile Icon={Icon} color={enabled ? color : "#8a96a5"} />
        <h2 className={`text-base font-semibold ${enabled ? "" : "text-muted"}`}>{SECTION_LABELS[sectionKey]}</h2>
        {count && <span className="rounded-full bg-desk px-2 py-0.5 text-xs font-medium text-muted">{count}</span>}
        <div className="ml-auto flex items-center gap-1">
          {enabled && (
            <>
              <Button variant="ghost" className="px-2" aria-label="Monter la section" disabled={index === 0} onClick={() => setSections((s) => move(s, index, -1))}>
                <ArrowUp className="size-4" aria-hidden />
              </Button>
              <Button variant="ghost" className="px-2" aria-label="Descendre la section" disabled={index === order.length - 1} onClick={() => setSections((s) => move(s, index, 1))}>
                <ArrowDown className="size-4" aria-hidden />
              </Button>
            </>
          )}
          <button
            type="button"
            role="switch"
            aria-checked={enabled}
            onClick={() => setSections((s) => (enabled ? s.filter((k) => k !== sectionKey) : [...s, sectionKey]))}
            className="ml-1 flex items-center gap-2 rounded-md px-2 py-1 text-sm hover:bg-ink/5"
          >
            <span className="relative h-5 w-9 rounded-full transition-colors" style={{ backgroundColor: enabled ? color : "#c5ced9" }}>
              <span className={`absolute top-0.5 size-4 rounded-full bg-white shadow transition-[left] ${enabled ? "left-4.5" : "left-0.5"}`} />
            </span>
            {enabled ? "Dans le CV" : "Masquée"}
          </button>
        </div>
      </header>
      <div className={`p-4 ${enabled ? "" : "opacity-70"}`}>{children}</div>
      {actions && <footer className="border-t border-line/70 px-4 py-2">{actions}</footer>}
    </section>
  );
}

/* ------------------------------------------------------------------ sections */

function IdentityCard() {
  const { cv, setBasics } = useCvActions();
  const b = cv.profile.basics;
  const text = (key: keyof Basics, label: string, type = "text") => (
    <Field label={label}>
      <Input type={type} value={String(b[key])} onChange={(e) => setBasics({ [key]: e.target.value })} />
    </Field>
  );
  return (
    <Card Icon={User} color="#334155" title="Identité et coordonnées">
      <div className="grid gap-3 sm:grid-cols-2">
        {text("full_name", "Nom complet")}
        {text("headline", "Titre professionnel")}
        {text("email", "Email", "email")}
        {text("phone", "Téléphone", "tel")}
        {text("location", "Ville, pays")}
        {text("linkedin_url", "Profil LinkedIn", "url")}
        <Field label="Autres liens (séparés par des virgules)" className="sm:col-span-2">
          <TagsInput value={b.websites} onChange={(websites) => setBasics({ websites })} />
        </Field>
      </div>
    </Card>
  );
}

function SummaryCard() {
  const { cv, setBasics } = useCvActions();
  return (
    <SectionShell sectionKey="summary">
      <Textarea
        aria-label="Résumé professionnel"
        rows={5}
        value={cv.profile.basics.summary}
        placeholder="Trois à cinq phrases : votre métier, vos années d'expérience, vos points forts et ce que vous cherchez."
        onChange={(e) => setBasics({ summary: e.target.value })}
      />
    </SectionShell>
  );
}

function SkillsCard() {
  const { cv, setItems } = useCvActions();
  const [draft, setDraft] = useState("");
  const items = cv.profile.skills;
  const add = () => {
    const names = draft.split(",").map((s) => s.trim()).filter(Boolean);
    const known = new Set(items.map((i) => String(i.name).toLowerCase()));
    setItems("skills", (list) => [
      ...list,
      ...names.filter((n) => !known.has(n.toLowerCase())).map((name) => ({ ...newItem("skills"), name })),
    ]);
    setDraft("");
  };
  return (
    <SectionShell sectionKey="skills" count={`${items.filter((i) => i.include).length} sur ${items.length} retenues`}>
      {items.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {items.map((it) => (
            <li key={it.id} className={`flex items-center rounded-full border text-sm ${it.include ? "border-ink/30" : "border-line text-muted"}`}>
              <button
                type="button"
                aria-pressed={it.include}
                onClick={() => setItems("skills", (l) => l.map((x) => (x.id === it.id ? { ...x, include: !x.include } : x)))}
                className="rounded-l-full py-1 pl-3 pr-1.5"
              >
                <span className={it.include ? "marked" : "line-through decoration-muted/50"}>{String(it.name)}</span>
              </button>
              <button
                type="button"
                aria-label={`Supprimer ${it.name}`}
                onClick={() => setItems("skills", (l) => l.filter((x) => x.id !== it.id))}
                className="rounded-r-full py-1 pl-1 pr-2.5 text-muted hover:text-danger"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-xs text-muted">Cliquez sur une compétence pour la retirer du CV sans la supprimer.</p>
      <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); add(); }}>
        <Input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Ajouter : Python, Gestion de projet…" aria-label="Nouvelles compétences" />
        <Button type="submit" variant="secondary" disabled={!draft.trim()}>Ajouter</Button>
      </form>
    </SectionShell>
  );
}

function ListCard({ sectionKey }: { sectionKey: ListKey }) {
  const { cv, setItems } = useCvActions();
  const { checkpoint } = useStore();
  const [open, setOpen] = useState<string | null>(null);
  const def = SECTIONS[sectionKey];
  const { color } = SECTION_STYLE[sectionKey];
  const items = cv.profile[sectionKey];
  const patch = (id: string, p: Partial<Item>) =>
    setItems(sectionKey, (l) => l.map((x) => (x.id === id ? ({ ...x, ...p } as Item) : x)));
  const remove = (it: Item) => {
    checkpoint(`suppression de « ${def.title(it) || "élément"} »`);
    setItems(sectionKey, (l) => l.filter((x) => x.id !== it.id));
  };

  return (
    <SectionShell
      sectionKey={sectionKey}
      count={items.length ? `${items.filter((i) => i.include).length} / ${items.length} retenus` : undefined}
      actions={
        <Button variant="ghost" style={{ color }} onClick={() => { const it = newItem(sectionKey); setItems(sectionKey, (l) => [...l, it]); setOpen(it.id); }}>
          <Plus className="size-4" aria-hidden /> Ajouter
        </Button>
      }
    >
      {items.length === 0 ? (
        <p className="text-sm text-muted">Rien dans cette section. Ajoutez un élément si besoin.</p>
      ) : (
        <ol className="divide-y divide-line/70">
          {items.map((it, i) => {
            const title = def.title(it) || "Sans titre";
            const expanded = open === it.id;
            return (
              <li key={it.id} className="py-1.5">
                <div className={`flex items-center gap-3 rounded-md px-1 py-1 ${expanded ? "bg-surface" : "hover:bg-surface"}`}>
                  <input
                    type="checkbox"
                    className="size-4 shrink-0"
                    style={{ accentColor: color }}
                    checked={it.include}
                    aria-label={`Inclure « ${title} » dans le CV`}
                    onChange={(e) => patch(it.id, { include: e.target.checked })}
                  />
                  <button type="button" className="min-w-0 flex-1 text-left text-sm" aria-expanded={expanded} onClick={() => setOpen(expanded ? null : it.id)}>
                    <span className={it.include ? "marked font-medium" : "text-muted line-through decoration-muted/50"}>{title}</span>
                    {(it.start || it.end || it.current) && (
                      <span className="ml-2 whitespace-nowrap text-xs text-muted">
                        {String(it.start || "")}{(it.end || it.current) && " – "}{it.current ? "aujourd'hui" : String(it.end || "")}
                      </span>
                    )}
                  </button>
                  <div className="flex shrink-0 items-center">
                    <Button variant="ghost" className="px-1.5 py-1" aria-label="Monter" disabled={i === 0} onClick={() => setItems(sectionKey, (l) => move(l, i, -1))}>
                      <ArrowUp className="size-4" aria-hidden />
                    </Button>
                    <Button variant="ghost" className="px-1.5 py-1" aria-label="Descendre" disabled={i === items.length - 1} onClick={() => setItems(sectionKey, (l) => move(l, i, 1))}>
                      <ArrowDown className="size-4" aria-hidden />
                    </Button>
                    <Button variant="ghost" className="px-2 py-1" aria-expanded={expanded} onClick={() => setOpen(expanded ? null : it.id)}>
                      <Pencil className="size-4" aria-hidden /> <span className="hidden sm:inline">{expanded ? "Fermer" : "Modifier"}</span>
                    </Button>
                  </div>
                </div>
                {expanded && (
                  <div className="mt-2 space-y-3 rounded-md border-l-3 bg-surface p-3 sm:ml-7" style={{ borderLeftColor: color }}>
                    <ItemFields item={it} fields={def.fields} onChange={(p) => patch(it.id, p)} />
                    <Button variant="danger" className="px-2" onClick={() => remove(it)}>
                      <Trash className="size-4" aria-hidden /> Supprimer cet élément
                    </Button>
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </SectionShell>
  );
}

/* ------------------------------------------------------------------ step */

export function EditStep() {
  const { cv, setStep, aiReady } = useStore();
  const { setItems } = useCvActions();
  const enabled = cv.settings.sections;
  // Enabled sections in CV order, then the hidden ones. Empty lists are folded into one "add" row.
  const order = [...enabled, ...ALL_SECTIONS.filter((k) => !enabled.includes(k))];
  const isEmpty = (k: SectionKey) => k !== "summary" && k !== "skills" && cv.profile[k].length === 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Choisissez ce qui va dans le CV</h1>
          <p className="mt-1 text-sm text-muted">
            Ce qui est <span className="marked text-ink">surligné</span> apparaît dans le CV. L&apos;aperçu et le score se mettent à jour en direct.
          </p>
        </div>
        {aiReady ? (
          <Button variant="ai" onClick={() => setStep("ai")}>
            <Sparkles className="size-4" aria-hidden /> Améliorer avec l&apos;agent IA
          </Button>
        ) : (
          <Button onClick={() => setStep("export")}>Passer à l&apos;export</Button>
        )}
      </div>
      <TargetCard />
      <IdentityCard />
      {order.filter((k) => !isEmpty(k)).map((key) =>
        key === "summary" ? <SummaryCard key={key} /> : key === "skills" ? <SkillsCard key={key} /> : <ListCard key={key} sectionKey={key} />,
      )}
      {order.some(isEmpty) && (
        <section className="flex flex-wrap items-center gap-2 rounded-lg border border-dashed border-line bg-white/50 px-4 py-3 text-sm">
          <span className="text-muted">Sections vides, à ajouter si besoin :</span>
          {(order.filter(isEmpty) as ListKey[]).map((k) => {
            const { color, Icon } = SECTION_STYLE[k];
            return (
              <Button key={k} variant="secondary" className="py-1" onClick={() => setItems(k, (l) => [...l, newItem(k)])}>
                <Icon className="size-4" style={{ color }} aria-hidden /> {SECTION_LABELS[k]}
              </Button>
            );
          })}
        </section>
      )}
    </div>
  );
}
