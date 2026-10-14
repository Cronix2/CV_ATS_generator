/** PasseFiltre mark: CV lines enter the ATS funnel, the CV that passes comes out highlighted. */
export function LogoMark({ className = "size-7" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <path d="M5 6h22l-8.2 9.6v7l-5.6 3v-10z" fill="var(--color-brand)" stroke="var(--color-brand)" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M9.5 9.2h13" stroke="#fff" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M12.2 12.2h7.6" stroke="#fff" strokeWidth="1.5" strokeLinecap="round" />
      <rect x="8" y="27" width="16" height="3.4" rx="1.7" fill="var(--color-mark)" />
    </svg>
  );
}

export function Logo() {
  return (
    <span className="flex items-center gap-2">
      <LogoMark />
      <span className="text-[17px] font-bold tracking-tight text-ink">
        Passe<span className="marked">Filtre</span>
      </span>
    </span>
  );
}
