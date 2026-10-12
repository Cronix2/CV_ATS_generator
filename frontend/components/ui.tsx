import type { LucideIcon } from "lucide-react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";

type Variant = "primary" | "ai" | "secondary" | "ghost" | "danger";
const VARIANTS: Record<Variant, string> = {
  primary: "bg-brand text-white hover:bg-brand/90 disabled:bg-brand/40 shadow-sm",
  ai: "bg-ai text-white hover:bg-ai/90 disabled:bg-ai/40 shadow-sm",
  secondary: "bg-white text-ink border border-line hover:border-brand hover:text-brand disabled:opacity-50",
  ghost: "text-muted hover:text-ink hover:bg-ink/5 disabled:opacity-40",
  danger: "text-danger hover:bg-danger/10 disabled:opacity-40",
};

export function Button({ variant = "primary", className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type="button"
      className={`inline-flex items-center justify-center gap-2 rounded-md px-3.5 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed ${VARIANTS[variant]} ${className}`}
      {...props}
    />
  );
}

const control =
  "w-full rounded-md border border-line bg-white px-3 py-2 text-sm text-ink placeholder:text-muted/60 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/15";

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${control} ${props.className ?? ""}`} />;
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea rows={5} {...props} className={`${control} leading-relaxed ${props.className ?? ""}`} />;
}

export function Field({ label, hint, children, className = "" }: { label: string; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1 block text-[13px] font-medium text-ink">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export function Alert({ tone = "danger", children }: { tone?: "danger" | "ok" | "info" | "ai"; children: ReactNode }) {
  const tones = {
    danger: "border-danger/30 bg-danger/5 text-danger",
    ok: "border-ok/30 bg-ok/5 text-ok",
    info: "border-brand/25 bg-brand-soft text-ink",
    ai: "border-ai/25 bg-ai-soft text-ink",
  };
  return <div role={tone === "danger" ? "alert" : "status"} className={`rounded-md border px-3 py-2 text-sm ${tones[tone]}`}>{children}</div>;
}

export function Spinner() {
  return <span aria-hidden className="inline-block size-4 animate-spin rounded-full border-2 border-current border-r-transparent" />;
}

/** Small coloured icon tile used in card headers. */
export function IconTile({ Icon, color }: { Icon: LucideIcon; color: string }) {
  return (
    <span className="grid size-8 shrink-0 place-items-center rounded-md" style={{ backgroundColor: `${color}18`, color }}>
      <Icon className="size-4.5" strokeWidth={2} aria-hidden />
    </span>
  );
}

export function Card({ Icon, color, title, aside, children, footer, className = "" }: {
  Icon?: LucideIcon; color?: string; title: ReactNode; aside?: ReactNode; children: ReactNode; footer?: ReactNode; className?: string;
}) {
  return (
    <section className={`overflow-hidden rounded-lg border border-line bg-white ${className}`} style={color ? { borderTopColor: color, borderTopWidth: 3 } : undefined}>
      <header className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-line/70 px-4 py-3">
        {Icon && color && <IconTile Icon={Icon} color={color} />}
        <h2 className="text-base font-semibold">{title}</h2>
        {aside && <div className="ml-auto flex items-center gap-1">{aside}</div>}
      </header>
      <div className="p-4">{children}</div>
      {footer && <footer className="border-t border-line/70 px-4 py-2">{footer}</footer>}
    </section>
  );
}

export function Chip({ tone = "neutral", children, onRemove }: { tone?: "neutral" | "ok" | "missing" | "ai"; children: ReactNode; onRemove?: () => void }) {
  const tones = {
    neutral: "border-line bg-white text-ink",
    ok: "border-ok/30 bg-ok/10 text-ok",
    missing: "border-danger/25 bg-danger/5 text-danger",
    ai: "border-ai/30 bg-ai-soft text-ai",
  };
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium ${tones[tone]}`}>
      {children}
      {onRemove && (
        <button type="button" onClick={onRemove} aria-label="Retirer" className="-mr-1 rounded-full px-1 opacity-60 hover:opacity-100">
          ×
        </button>
      )}
    </span>
  );
}
