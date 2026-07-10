export const BROWSER_APPROVAL_TOKEN_STORAGE_KEY = "rumi.authority.browserApprovalToken";

const BROWSER_APPROVAL_TOKEN_PARAM_KEYS = [
  "browser_approval_token",
  "approval_browser_token",
  "browserApprovalToken",
] as const;

const LEGACY_AUTHORITY_SETTLEMENT_PARAM_KEYS = [
  "authority_approved",
] as const;

export function readBrowserApprovalTokenFromLocation(search = locationSearch()): string {
  if (arguments.length === 0) clearLegacyAuthoritySettlementParamsFromLocation();
  try {
    const params = new URLSearchParams(search);
    for (const key of BROWSER_APPROVAL_TOKEN_PARAM_KEYS) {
      const token = params.get(key)?.trim();
      if (token) return token;
    }
  } catch {
    return "";
  }
  return "";
}

export function readBrowserApprovalTokenFromStorage(): string {
  return readBrowserApprovalTokenFromSessionStorage() || readBrowserApprovalTokenFromLocalStorage();
}

export function readBrowserApprovalToken(): string {
  return readBrowserApprovalTokenFromLocation() || readBrowserApprovalTokenFromStorage();
}

export function rememberBrowserApprovalToken(token: string): void {
  const normalized = token.trim();
  writeStorageValue("sessionStorage", normalized);
  writeStorageValue("localStorage", normalized);
}

export function browserAuthorityApprovalPath(requestId: string, browserApprovalToken: string, returnTo = ""): string {
  const params = new URLSearchParams();
  params.set("request_id", requestId);
  const token = browserApprovalToken.trim();
  if (token) params.set("browser_approval_token", token);
  const normalizedReturnTo = stripLegacyAuthoritySettlementParamsFromPath(returnTo.trim());
  if (normalizedReturnTo) params.set("return_to", normalizedReturnTo);
  return `/approval?${params.toString()}`;
}

export function stripLegacyAuthoritySettlementParamsFromPath(pathOrUrl: string): string {
  if (!pathOrUrl) return pathOrUrl;
  try {
    const hasWindow = typeof window !== "undefined";
    const base = hasWindow ? window.location.origin : "http://127.0.0.1";
    const relativeSameOriginPath = pathOrUrl.startsWith("/") && !pathOrUrl.startsWith("//");
    const url = new URL(pathOrUrl, base);
    for (const key of LEGACY_AUTHORITY_SETTLEMENT_PARAM_KEYS) {
      url.searchParams.delete(key);
    }
    if ((hasWindow && url.origin === window.location.origin) || (!hasWindow && relativeSameOriginPath)) {
      return `${url.pathname}${url.search}${url.hash}`;
    }
    return url.toString();
  } catch {
    return pathOrUrl;
  }
}

export function clearLegacyAuthoritySettlementParamsFromLocation(): void {
  try {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    let changed = false;
    for (const key of LEGACY_AUTHORITY_SETTLEMENT_PARAM_KEYS) {
      if (!url.searchParams.has(key)) continue;
      url.searchParams.delete(key);
      changed = true;
    }
    if (!changed) return;
    window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
  } catch {
    // Location/history may be unavailable in restricted webviews and tests.
  }
}

export function browserApprovalTokenizedPath(pathOrUrl: string, browserApprovalToken = readBrowserApprovalToken()): string {
  const sanitizedPathOrUrl = stripLegacyAuthoritySettlementParamsFromPath(pathOrUrl);
  const token = browserApprovalToken.trim();
  if (!token) return sanitizedPathOrUrl;
  try {
    const hasWindow = typeof window !== "undefined";
    const base = hasWindow ? window.location.origin : "http://127.0.0.1";
    const relativeSameOriginPath = sanitizedPathOrUrl.startsWith("/") && !sanitizedPathOrUrl.startsWith("//");
    const url = new URL(sanitizedPathOrUrl, base);
    if (!url.searchParams.get("browser_approval_token")?.trim()) {
      url.searchParams.set("browser_approval_token", token);
    }
    if ((hasWindow && url.origin === window.location.origin) || (!hasWindow && relativeSameOriginPath)) {
      return `${url.pathname}${url.search}${url.hash}`;
    }
    return url.toString();
  } catch {
    const separator = sanitizedPathOrUrl.includes("?") ? "&" : "?";
    return `${sanitizedPathOrUrl}${separator}browser_approval_token=${encodeURIComponent(token)}`;
  }
}

function locationSearch(): string {
  try {
    return typeof window === "undefined" ? "" : window.location.search;
  } catch {
    return "";
  }
}

function readBrowserApprovalTokenFromSessionStorage(): string {
  return readStorageValue("sessionStorage");
}

function readBrowserApprovalTokenFromLocalStorage(): string {
  return readStorageValue("localStorage");
}

function readStorageValue(kind: "sessionStorage" | "localStorage"): string {
  try {
    return window[kind].getItem(BROWSER_APPROVAL_TOKEN_STORAGE_KEY)?.trim() ?? "";
  } catch {
    return "";
  }
}

function writeStorageValue(kind: "sessionStorage" | "localStorage", value: string): void {
  try {
    if (value) window[kind].setItem(BROWSER_APPROVAL_TOKEN_STORAGE_KEY, value);
    else window[kind].removeItem(BROWSER_APPROVAL_TOKEN_STORAGE_KEY);
  } catch {
    // Browser storage may be unavailable in restricted webviews or private contexts.
  }
}
