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

const DIAGNOSTIC_SCHEMA_VERSION = "client-diagnostic.v1";
const DIAGNOSTIC_TTL_MS = 30_000;
const MAX_DETAIL_DEPTH = 4;
const MAX_DETAIL_ITEMS = 20;
const MAX_DETAIL_BYTES = 8_000;
const sentDiagnostics = new Map<string, number>();
let listenersInstalled = false;

const SAFE_DETAIL_KEYS = new Set([
  "build",
  "category",
  "code",
  "colno",
  "column",
  "component",
  "count",
  "error_name",
  "kind",
  "level",
  "line",
  "lineno",
  "name",
  "operation",
  "phase",
  "reason",
  "retryable",
  "source",
  "source_location",
  "stack",
  "status",
  "type",
]);

const SENSITIVE_KEY_PATTERN = /(authorization|cookie|credential|password|passwd|secret|token|api[_-]?key|prompt|message|content|body|input|output|result|argument|payload|header|email|file|path|url|conversation|resource)/i;

function stableHash(value: string): string {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

function compactIdentifier(value: unknown, fallback: string, maxLength: number): string {
  const normalized = String(value ?? fallback)
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, maxLength);
  return normalized || fallback;
}

export function opaqueDiagnosticContextId(value: unknown): string | undefined {
  const normalized = String(value ?? "").trim();
  return normalized ? `ctx_${stableHash(normalized)}` : undefined;
}

export function redactClientDiagnosticText(value: unknown, fallback = "frontend diagnostic", maxLength = 500): string {
  let text = String(value ?? fallback).trim().replace(/\s+/g, " ");
  if (!text) text = fallback;

  text = text
    .replace(/\b(?:authorization|proxy-authorization)\s*[:=]\s*(?:bearer|basic)?\s*[^\s,;]+/gi, "authorization=[redacted]")
    .replace(/\b(?:bearer|basic)\s+[a-z0-9._~+/=-]{8,}/gi, "[redacted-authorization]")
    .replace(/\beyj[a-z0-9_-]{8,}\.[a-z0-9_-]{8,}\.[a-z0-9_-]{8,}\b/gi, "[redacted-jwt]")
    .replace(/\b(?:sk-[a-z0-9_-]{8,}|gh[pousr]_[a-z0-9_]{8,}|github_pat_[a-z0-9_]{8,}|akia[0-9a-z]{16}|aiza[0-9a-z_-]{20,}|xox[baprs]-[a-z0-9-]{8,})\b/gi, "[redacted-token]")
    .replace(/\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|secret|password|passwd|cookie|session|credential)\s*[:=]\s*["']?[^\s,"';}]+/gi, "credential=[redacted]")
    .replace(/\b(?:https?|wss?|file|data|javascript):[^\s<>"']+/gi, "[redacted-url]")
    .replace(/\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b/gi, "[redacted-email]")
    .replace(/\b[a-z]:\\(?:[^\\\s]+\\)*[^\\\s]*/gi, "[redacted-path]")
    .replace(/(^|[\s("'`])\/(?:users|home|private|tmp|var|etc|opt|workspace|workspaces|mnt)\/[^\s)"'`]*/gi, "$1[redacted-path]")
    .replace(/(["'])(?:\\.|(?!\1).){24,}\1/g, '"[redacted-text]"')
    .replace(/\b[a-z0-9+/_=-]{40,}\b/gi, "[redacted-value]");

  return text.slice(0, maxLength);
}

function sanitizeStack(value: unknown): string | undefined {
  const stack = String(value ?? "").trim();
  if (!stack) return undefined;
  return stack
    .split(/\r?\n/)
    .slice(0, 20)
    .map((line) => redactClientDiagnosticText(line, "", 500))
    .filter(Boolean)
    .join("\n")
    .slice(0, 4_000);
}

function normalizeDetail(
  value: unknown,
  depth = 0,
  seen: WeakSet<object> = new WeakSet<object>(),
): unknown {
  if (depth >= MAX_DETAIL_DEPTH) return "[truncated]";
  if (value === null || value === undefined || typeof value === "boolean" || typeof value === "number") return value;
  if (typeof value === "string") return redactClientDiagnosticText(value, "", 1_000);
  if (typeof value === "bigint") return value.toString();
  if (typeof value !== "object") return compactIdentifier(typeof value, "unknown", 32);

  if (seen.has(value)) return "[circular]";
  seen.add(value);

  if (Array.isArray(value)) {
    return value.slice(0, MAX_DETAIL_ITEMS).map((item) => normalizeDetail(item, depth + 1, seen));
  }

  const entries: Array<[string, unknown]> = [];
  for (const [rawKey, item] of Object.entries(value as Record<string, unknown>).slice(0, MAX_DETAIL_ITEMS * 2)) {
    const key = compactIdentifier(rawKey, "field", 64);
    if (SENSITIVE_KEY_PATTERN.test(rawKey)) {
      entries.push([key, "[redacted]"]);
      continue;
    }
    if (!SAFE_DETAIL_KEYS.has(key)) continue;
    if (key === "stack") {
      entries.push([key, sanitizeStack(item)]);
      continue;
    }
    entries.push([key, normalizeDetail(item, depth + 1, seen)]);
  }
  return Object.fromEntries(entries.filter(([, item]) => item !== undefined));
}

function boundedDetail(value: unknown): Record<string, unknown> {
  const detail = {
    schema_version: DIAGNOSTIC_SCHEMA_VERSION,
    fields: normalizeDetail(value),
  };
  try {
    if (JSON.stringify(detail).length <= MAX_DETAIL_BYTES) return detail;
  } catch {
    return { schema_version: DIAGNOSTIC_SCHEMA_VERSION, fields: "[unserializable]" };
  }
  return { schema_version: DIAGNOSTIC_SCHEMA_VERSION, fields: "[payload-truncated]" };
}

export function diagnosticFingerprint(input: ClientDiagnosticInput): string {
  const source = compactIdentifier(input.source, "webapp", 80);
  const category = compactIdentifier(input.category, "frontend", 80);
  const safeMessage = redactClientDiagnosticText(input.message, "frontend diagnostic", 240);
  const contextId = opaqueDiagnosticContextId(input.conversationId) ?? "";
  const callerFingerprint = String(input.fingerprint ?? "").trim();
  return `fp_${stableHash([source, category, safeMessage, contextId, callerFingerprint].join(":"))}`;
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
    source: compactIdentifier(input.source, "webapp", 80),
    category: compactIdentifier(input.category, "frontend", 80),
    level: compactIdentifier(input.level, "error", 24),
    message: redactClientDiagnosticText(input.message, "frontend diagnostic", 600),
    fingerprint: diagnosticFingerprint(input),
    conversation_id: opaqueDiagnosticContextId(input.conversationId),
    detail: boundedDetail(input.detail),
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
    sentDiagnostics.delete(normalized.fingerprint);
    return false;
  }
}

function errorName(value: unknown): string {
  return value instanceof Error ? compactIdentifier(value.name, "error", 48) : compactIdentifier(typeof value, "unknown", 48);
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
      message: "Unhandled window error",
      detail: {
        error_name: errorName(event.error),
        source_location: event.filename,
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
      message: "Unhandled promise rejection",
      detail: {
        error_name: errorName(reason),
        stack: reason instanceof Error ? reason.stack : undefined,
        reason: reason instanceof Error ? undefined : { type: typeof reason },
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
