import type { ChatUiMessage } from "../renderers/types";

export type BrowserApproval = {
  action: string;
  payload: Record<string, unknown>;
  token: string;
  toolName: string;
};

const BROWSER_COMPUTER_TOOL_NAMES = new Set([
  "browser_computer",
  "browser_companion",
  "browser_use",
  "computer_use",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function numericTimestamp(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value > 10_000_000_000 ? value : value * 1000;
  }
  if (typeof value === "string" && value.trim()) {
    const numeric = Number(value);
    if (Number.isFinite(numeric)) return numericTimestamp(numeric);
    const parsed = Date.parse(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function approvalExpired(candidate: Record<string, unknown>, observedAt: unknown, now: number): boolean {
  const expiresAt = numericTimestamp(candidate.expires_at);
  if (expiresAt !== null) return expiresAt <= now;

  const expiresInSeconds = Number(candidate.approval_expires_in_seconds);
  const timestamp = numericTimestamp(candidate.timestamp ?? observedAt);
  if (Number.isFinite(expiresInSeconds) && expiresInSeconds > 0 && timestamp !== null) {
    return timestamp + expiresInSeconds * 1000 <= now;
  }
  return false;
}

function approvalFromCandidate(
  candidate: Record<string, unknown> | undefined,
  fallbackToolName = "browser_computer",
  observedAt: unknown,
  now: number,
): BrowserApproval | null {
  if (!candidate?.requires_approval && !candidate?.approval_required) return null;
  if (!candidate.approval_token) return null;
  const token = String(candidate.approval_token);
  if (!token.trim() || token === "[redacted]") return null;
  if (approvalExpired(candidate, observedAt, now)) return null;
  const rawPayload = candidate.payload;
  const toolName = String(candidate.tool_name ?? fallbackToolName);
  return {
    action: String(candidate.action ?? "browser.session"),
    payload: isRecord(rawPayload) ? rawPayload : {},
    token,
    toolName,
  };
}

export function pendingBrowserApproval(messages: ChatUiMessage[], now = Date.now()): BrowserApproval | null {
  for (const message of [...messages].reverse()) {
    if (message.role === "user") return null;
    if (message.role !== "agent") continue;
    for (const event of [...(message.events ?? [])].reverse()) {
      if (event.type !== "approval_requested" && event.phase !== "approval_requested") continue;
      const approval = approvalFromCandidate(
        event as Record<string, unknown>,
        String(event.tool_name ?? "browser_computer"),
        event.timestamp,
        now,
      );
      if (approval) return approval;
    }
    for (const log of [...(message.toolLogs ?? [])].reverse()) {
      if (!BROWSER_COMPUTER_TOOL_NAMES.has(String(log.tool_name))) continue;
      const result = isRecord(log.result) ? log.result : undefined;
      const data = isRecord(result?.data) ? result.data : result;
      const widget = isRecord(data?.widget) ? data.widget : undefined;
      const candidate = (widget?.requires_approval || widget?.approval_required ? widget : data) as Record<string, unknown> | undefined;
      const approval = approvalFromCandidate(candidate, String(log.tool_name), log.timestamp, now);
      if (approval) return approval;
    }
  }
  return null;
}
