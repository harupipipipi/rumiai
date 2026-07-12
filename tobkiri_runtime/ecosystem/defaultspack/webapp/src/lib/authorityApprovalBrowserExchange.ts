import {
  api,
  type AuthorityApprovalContext,
  type AuthorityBrowserExchangeBinding,
} from "./api";

export type BrowserApprovalExchangeState =
  | "idle"
  | "issuing"
  | "ready"
  | "redeeming"
  | "settled"
  | "expired"
  | "revoked"
  | "error";

type PendingExchange = {
  binding: AuthorityBrowserExchangeBinding;
  code: string;
  exchangeId: string;
  expiresAtMs: number;
};

export type BrowserApprovalExchangeTransport = {
  issue(binding: AuthorityBrowserExchangeBinding): Promise<{
    request_id: string;
    exchange_code: string;
    exchange_id: string;
    expires_at: number | string;
  }>;
  redeem(binding: AuthorityBrowserExchangeBinding, code: string): Promise<AuthorityApprovalContext>;
  revoke(binding: AuthorityBrowserExchangeBinding, exchangeId: string): Promise<{ revoked: boolean }>;
};

const defaultTransport: BrowserApprovalExchangeTransport = {
  issue: (binding) => api.createBrowserAuthorityExchange(binding),
  redeem: (binding, code) => api.browserAuthorityUiOperator(binding, code),
  revoke: (binding, exchangeId) => api.revokeBrowserAuthorityExchange(binding, exchangeId),
};

const pageDeviceId = secureRandomId("device");
const pageWindowId = secureRandomId("window");

/** A memory-only, request-bound, single-use browser approval exchange. */
export class BrowserApprovalExchangeSession {
  private pending: PendingExchange | null = null;
  private currentState: BrowserApprovalExchangeState = "idle";
  private generation = 0;

  constructor(
    private readonly transport: BrowserApprovalExchangeTransport = defaultTransport,
    private readonly now: () => number = Date.now,
    private readonly identity: { deviceId: string; windowId: string; origin: string } = {
      deviceId: pageDeviceId,
      windowId: pageWindowId,
      origin: browserOrigin(),
    },
  ) {}

  get state(): BrowserApprovalExchangeState {
    return this.currentState;
  }

  async context(requestId: string): Promise<AuthorityApprovalContext> {
    await this.revoke();
    const generation = ++this.generation;
    const binding = this.newBinding(requestId);
    this.currentState = "issuing";
    try {
      const issued = await this.transport.issue(binding);
      if (issued.request_id !== binding.request_id || !issued.exchange_code || !issued.exchange_id) {
        throw new Error("AUTHORITY_BROWSER_EXCHANGE_INVALID");
      }
      if (generation !== this.generation) {
        await this.transport.revoke(binding, issued.exchange_id);
        this.currentState = "revoked";
        throw new Error("AUTHORITY_BROWSER_EXCHANGE_REVOKED");
      }
      const expiresAtMs = normalizeExpiryMs(issued.expires_at);
      if (!Number.isFinite(expiresAtMs) || expiresAtMs <= this.now()) {
        this.currentState = "expired";
        throw new Error("AUTHORITY_BROWSER_EXCHANGE_EXPIRED");
      }
      this.pending = { binding, code: issued.exchange_code, exchangeId: issued.exchange_id, expiresAtMs };
      this.currentState = "ready";
      return await this.redeem(requestId);
    } catch (error) {
      if (this.currentState !== "expired" && this.currentState !== "revoked") {
        this.currentState = exchangeFailureState(error);
      }
      throw error;
    }
  }

  async revoke(): Promise<boolean> {
    this.generation += 1;
    const pending = this.pending;
    this.pending = null;
    if (!pending) return false;
    try {
      await this.transport.revoke(pending.binding, pending.exchangeId);
    } finally {
      this.currentState = "revoked";
    }
    return true;
  }

  private async redeem(requestId: string): Promise<AuthorityApprovalContext> {
    const pending = this.pending;
    if (!pending || pending.binding.request_id !== requestId) {
      this.currentState = "error";
      throw new Error("AUTHORITY_BROWSER_EXCHANGE_WRONG_REQUEST");
    }
    if (pending.expiresAtMs <= this.now()) {
      await this.revoke();
      this.currentState = "expired";
      throw new Error("AUTHORITY_BROWSER_EXCHANGE_EXPIRED");
    }
    // Remove the code from live state before the consuming request to prevent races.
    this.pending = null;
    this.currentState = "redeeming";
    const context = await this.transport.redeem(pending.binding, pending.code);
    if (context.request_id !== requestId || context.ui_operator.request_id !== requestId) {
      this.currentState = "error";
      throw new Error("AUTHORITY_BROWSER_EXCHANGE_WRONG_REQUEST");
    }
    this.currentState = "settled";
    return context;
  }

  private newBinding(requestId: string): AuthorityBrowserExchangeBinding {
    const normalizedRequestId = requestId.trim();
    if (!normalizedRequestId || !this.identity.origin || !this.identity.deviceId || !this.identity.windowId) {
      throw new Error("AUTHORITY_BROWSER_EXCHANGE_BINDING_INVALID");
    }
    return {
      request_id: normalizedRequestId,
      device_id: this.identity.deviceId,
      window_id: this.identity.windowId,
      nonce: secureRandomId("nonce"),
      origin: this.identity.origin,
    };
  }
}

function browserOrigin(): string {
  try {
    return typeof window === "undefined" ? "http://127.0.0.1" : window.location.origin;
  } catch {
    return "";
  }
}

function secureRandomId(prefix: string): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    const bytes = crypto.getRandomValues(new Uint8Array(24));
    return `${prefix}-${Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("")}`;
  }
  // Approval fails closed in newBinding when a cryptographic source is unavailable.
  return "";
}

function exchangeFailureState(error: unknown): BrowserApprovalExchangeState {
  const message = error instanceof Error ? error.message : String(error ?? "");
  if (message.includes("REVOKED")) return "revoked";
  if (message.includes("EXPIRED") || message.includes("HTTP 410")) return "expired";
  return "error";
}

function normalizeExpiryMs(value: number | string): number {
  if (typeof value === "number") return Number.isFinite(value) ? value * 1000 : Number.NaN;
  const numeric = Number(value);
  if (Number.isFinite(numeric) && value.trim()) return numeric * 1000;
  return Date.parse(value);
}
