import { scrapeLinkedInProfile } from "@/lib/linkedin-scraper";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type PendingMfaChallenge = {
  resolve: (code: string) => void;
  timeoutId: NodeJS.Timeout;
};

const MFA_TIMEOUT_MS = 5 * 60 * 1000;
const pendingMfaChallenges = new Map<string, PendingMfaChallenge>();

function cleanupMfaChallenge(requestId: string) {
  const pending = pendingMfaChallenges.get(requestId);
  if (!pending) return;
  clearTimeout(pending.timeoutId);
  pendingMfaChallenges.delete(requestId);
}

function waitForMfaCode(requestId: string): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const timeoutId = setTimeout(() => {
      pendingMfaChallenges.delete(requestId);
      reject(new Error("Délai expiré pour le code de vérification LinkedIn."));
    }, MFA_TIMEOUT_MS);

    pendingMfaChallenges.set(requestId, {
      resolve: (code: string) => {
        clearTimeout(timeoutId);
        resolve(code);
      },
      timeoutId,
    });
  });
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const profileUrl = searchParams.get("url");
  const requestId = crypto.randomUUID();

  if (!profileUrl) {
    return new Response(JSON.stringify({ error: "URL manquante" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const linkedinPattern = /^https?:\/\/(www\.)?linkedin\.com\/in\/[\w%-]+\/?$/;
  if (!linkedinPattern.test(profileUrl)) {
    return new Response(JSON.stringify({ error: "URL LinkedIn invalide" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    async start(controller) {
      function sendEvent(event: string, data: unknown) {
        controller.enqueue(
          encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
        );
      }

      try {
        const result = await scrapeLinkedInProfile(
          profileUrl,
          (progress) => {
            sendEvent("progress", progress);
          },
          async (ctx) => {
            sendEvent("mfa_required", {
              requestId,
              message: ctx.reason,
              url: ctx.url,
              timeoutSeconds: MFA_TIMEOUT_MS / 1000,
            });
            return await waitForMfaCode(requestId);
          }
        );

        sendEvent("complete", result);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Erreur inconnue";
        sendEvent("error", { error: message });
      } finally {
        cleanupMfaChallenge(requestId);
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as { requestId?: string; code?: string };
    const requestId = body.requestId?.trim();
    const code = body.code?.trim();

    if (!requestId || !code) {
      return new Response(JSON.stringify({ error: "requestId et code requis" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    const pending = pendingMfaChallenges.get(requestId);
    if (!pending) {
      return new Response(JSON.stringify({ error: "Session MFA introuvable ou expirée" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    }

    cleanupMfaChallenge(requestId);
    pending.resolve(code);

    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return new Response(JSON.stringify({ error: "Requête invalide" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }
}
