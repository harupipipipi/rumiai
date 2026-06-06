import { api } from "./api";

export type ClientDiagnosticInput = {
  source?: string;
  category?: string;
  level?: "info" | "warning" | "error" | string;
  message: string;
  fingerprint?: string;
  conversationId?: string | null;
  detail?: unknown;
};

const DIAGNOSTIC_TTL_MS = 30_000;
const sentDiagnostics = new Map<string, number>();
let listenersInstalled = false;

function compactText(value: unknown, fallback: string, maxLength = 500): string {
  const text = String(value ?? fallback).trim().replace(/\s+/g, " ");
  return (text || fallback).slice(0, maxLength);
}

function normalizeDetail(value: unknown, depth = 0): unknown {
  if (depth >= 5) return "[truncated]";
  if (Array.isArray(value)) return value.slice(0, 30).map((item) => normalizeDetail(item, depth + 1));
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .slice(0, 30)
        .map(([key, item]) => [key, normalizeDetail(item, depth + 1)]),
    );
  }
  if (typeof value === "string") return value.slice(0, 2_000);
  return value;
}

export function diagnosticFingerprint(input: ClientDiagnosticInput): string {
  return [
    input.source ?? "webapp",
    input.category ?? "frontend",
    compactText(input.message, "frontend diagnostic", 160),
    input.conversationId ?? "",
  ].join(":");
}

function pruneDiagnosticCache(now: number) {
  for (const [fingerprint, timestamp] of sentDiagnostics.entries()) {
    if (now - timestamp > DIAGNOSTIC_TTL_MS) {
      sentDiagnostics.delete(fingerprint);
    }
  }
}

export async function reportClientDiagnostic(input: ClientDiagnosticInput): Promise<boolean> {
  const normalized = {
    source: compactText(input.source, "webapp", 80),
    category: compactText(input.category, "frontend", 80),
    level: compactText(input.level, "error", 24),
    message: compactText(input.message, "frontend diagnostic", 600),
    fingerprint: compactText(input.fingerprint, diagnosticFingerprint(input), 160),
    conversation_id: input.conversationId ? compactText(input.conversationId, "", 120) : undefined,
    detail: normalizeDetail(input.detail),
  };
  const now = Date.now();
  pruneDiagnosticCache(now);
  const lastSentAt = sentDiagnostics.get(normalized.fingerprint);
  if (lastSentAt && now - lastSentAt < DIAGNOSTIC_TTL_MS) {
    return false;
  }
  sentDiagnostics.set(normalized.fingerprint, now);
  try {
    await api.reportClientEvent(normalized);
    return true;
  } catch {
    return false;
  }
}

export function installGlobalClientDiagnostics(
  context?: () => Partial<Omit<ClientDiagnosticInput, "message">>,
): () => void {
  if (listenersInstalled || typeof window === "undefined") {
    return () => undefined;
  }
  listenersInstalled = true;

  const sharedContext = () => context?.() ?? {};

  const onError = (event: ErrorEvent) => {
    void reportClientDiagnostic({
      ...sharedContext(),
      source: "window.error",
      category: "window_error",
      level: "error",
      message: event.message || "Unhandled window error",
      detail: {
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
        stack: event.error instanceof Error ? event.error.stack : undefined,
      },
    });
  };

  const onUnhandledRejection = (event: PromiseRejectionEvent) => {
    const reason = event.reason;
    void reportClientDiagnostic({
      ...sharedContext(),
      source: "window.unhandledrejection",
      category: "promise_rejection",
      level: "error",
      message: reason instanceof Error ? reason.message : compactText(reason, "Unhandled promise rejection"),
      detail: {
        stack: reason instanceof Error ? reason.stack : undefined,
        reason: reason instanceof Error ? undefined : normalizeDetail(reason),
      },
    });
  };

  window.addEventListener("error", onError);
  window.addEventListener("unhandledrejection", onUnhandledRejection);

  return () => {
    listenersInstalled = false;
    window.removeEventListener("error", onError);
    window.removeEventListener("unhandledrejection", onUnhandledRejection);
  };
}
