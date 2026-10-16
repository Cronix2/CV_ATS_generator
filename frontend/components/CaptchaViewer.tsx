"use client";

import type RFB from "@novnc/novnc";
import { X } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { api } from "@/lib/api";
import { modalKeyAction } from "@/lib/modalKeys";
import { Alert, Button, Spinner } from "./ui";

const clock = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Remote view of the server's browser (noVNC), so the user can solve LinkedIn's CAPTCHA by hand.
 * The connection uses a single-use ticket bound to this job; closing the viewer does NOT validate
 * anything: the server only resumes once LinkedIn itself has accepted the verification.
 */
export function CaptchaViewer({ jobId, expiresIn, onClose }: { jobId: string; expiresIn: number | null | undefined; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const screen = useRef<HTMLDivElement>(null);
  const remote = useRef<RFB | null>(null);
  const [state, setState] = useState<"connecting" | "connected" | "closed">("connecting");
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  // Native modal: showModal() makes the rest of the page inert (no Tab, no click, hidden from screen
  // readers). Focus goes to the first control on opening and back to the opener on closing.
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const el = dialog.current;
    el?.showModal();
    el?.querySelector<HTMLElement>(FOCUSABLE)?.focus();
    return () => {
      el?.close();
      if (opener?.isConnected) opener.focus();
    };
  }, []);

  useEffect(() => {
    let rfb: RFB | null = null;
    let stopped = false;
    setState("connecting");
    setError("");
    (async () => {
      try {
        const [{ default: Client }, t] = await Promise.all([import("@novnc/novnc"), api.captchaTicket(jobId)]);
        if (stopped || !screen.current) return;
        rfb = remote.current = new Client(screen.current, api.captchaSocketUrl(jobId), { wsProtocols: ["binary", t.protocol + t.ticket] });
        rfb.scaleViewport = true;
        rfb.resizeSession = false;
        rfb.focusOnClick = true;
        rfb.addEventListener("connect", () => {
          setState("connected");
          rfb?.focus();
        });
        rfb.addEventListener("disconnect", () => {
          if (!stopped) setState("closed");
        });
      } catch (err) {
        if (!stopped) {
          setError((err as Error).message);
          setState("closed");
        }
      }
    })();
    return () => {
      stopped = true;
      remote.current = null;
      rfb?.disconnect();
    };
  }, [jobId, attempt]);

  // Capture phase: runs before noVNC's own listener on its canvas, which forwards every key to the server.
  const onKey = (e: KeyboardEvent<HTMLDialogElement>) => {
    const items = [...(dialog.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])];
    const inScreen = !!screen.current?.contains(e.target as Node) && e.target !== screen.current;
    const action = modalKeyAction(e, inScreen, items.indexOf(e.target as HTMLElement), items.length);
    if (!action) return;
    e.preventDefault();
    e.stopPropagation();
    if (action.type === "close") onClose();
    else if (action.type === "release") items[0]?.focus();
    else items[action.index]?.focus();
  };

  return (
    <dialog
      ref={dialog}
      aria-labelledby="captcha-title"
      onKeyDownCapture={onKey}
      onCancel={(e) => {
        e.preventDefault(); // other close requests (e.g. Android back): let the parent unmount us
        onClose();
      }}
      className="fixed inset-0 m-0 size-full max-h-none max-w-none items-center justify-center bg-ink/60 p-2 open:flex backdrop:bg-transparent sm:p-6"
    >
      <div className="flex max-h-full w-full max-w-5xl flex-col overflow-hidden rounded-lg bg-white shadow-xl">
        <header className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line px-4 py-3">
          <h2 id="captcha-title" className="text-base font-semibold">Résoudre le CAPTCHA LinkedIn</h2>
          {typeof expiresIn === "number" && <span className="text-sm text-muted">Temps restant : {clock(expiresIn)}</span>}
          <Button variant="ghost" className="ml-auto" onClick={onClose} aria-label="Fermer la fenêtre">
            <X className="size-4" aria-hidden /> Fermer
          </Button>
        </header>
        <p className="px-4 pt-3 text-sm text-muted">
          Vous pilotez le navigateur du serveur. Résolvez le CAPTCHA ; PasseFiltre reprend tout seul dès que LinkedIn
          confirme la vérification. Fermer cette fenêtre ne valide rien.
        </p>
        <div className="relative m-4 min-h-0 flex-1">
          <div
            ref={screen}
            tabIndex={state === "connected" ? 0 : -1}
            aria-label="Écran du navigateur du serveur"
            onFocus={(e) => {
              if (e.target === e.currentTarget) remote.current?.focus();
            }}
            className="aspect-[1280/900] max-h-[70vh] w-full overflow-hidden rounded-md border border-line bg-ink"
          />
          {state !== "connected" && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 rounded-md bg-white/90 p-4 text-center text-sm">
              {state === "connecting" ? (
                <span className="flex items-center gap-2"><Spinner /> Connexion au navigateur du serveur…</span>
              ) : (
                <>
                  {error ? <Alert>{error}</Alert> : <p>La connexion au navigateur du serveur est fermée.</p>}
                  <Button variant="secondary" onClick={() => setAttempt((n) => n + 1)}>Se reconnecter</Button>
                </>
              )}
            </div>
          )}
        </div>
        {state === "connected" && (
          <p className="px-4 pb-3 text-xs text-muted">
            Le clavier (Échap et Tab compris) est transmis au navigateur du serveur. F8 pour revenir aux boutons
            de cette fenêtre.
          </p>
        )}
      </div>
    </dialog>
  );
}
