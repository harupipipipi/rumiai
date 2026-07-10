export const BROWSER_APPROVAL_TOKEN_STORAGE_KEY = "rumi.authority.browserApprovalToken";

const BROWSER_APPROVAL_TOKEN_PARAM_KEYS = [
  "browser_approval_token",
  "approval_browser_token",
  "browserApprovalToken",
] as const;

export function readBrowserApprovalTokenFromLocation(search = locationSearch()): string {
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
  // A reusable approval credential must not survive a browser/profile restart.
  // Remove any legacy localStorage value as part of the read path so existing
  // installations migrate toward session-only handling.
  removeStorageValue("localStorage");
  return readStorageValue("sessionStorage");
}

export function readBrowserApprovalToken(): string {
  return readBrowserApprovalTokenFromLocation() || readBrowserApprovalTokenFromStorage();
}

export function rememberBrowserApprovalToken(token: string): void {
  const normalized = token.trim();
  writeStorageValue("sessionStorage", normalized);
  removeStorageValue("localStorage");
}

export function clearBrowserApprovalToken(): void {
  removeStorageValue("sessionStorage");
  removeStorageValue("localStorage");
}

export function browserAuthorityApprovalPath(requestId: string, browserApprovalToken: string, returnTo = ""): string {
  const params = new URLSearchParams();
  params.set("request_id", requestId);
  const token = browserApprovalToken.trim();
  if (token) params.set("browser_approval_token", token);
  const normalizedReturnTo = sameOriginRelativePath(returnTo);
  if (normalizedReturnTo) params.set("return_to", normalizedReturnTo);
  return `/approval?${params.toString()}`;
}

export function browserApprovalTokenizedPath(pathOrUrl: string, browserApprovalToken = readBrowserApprovalToken()): string {
  const token = browserApprovalToken.trim();
  if (!token) return pathOrUrl;

  // Never transform an external, protocol-relative, or malformed destination.
  // In particular, the approval token must not be appended before the origin
  // policy has been checked.
  const url = sameOriginUrl(pathOrUrl);
  if (!url) return pathOrUrl;

  if (!url.searchParams.get("browser_approval_token")?.trim()) {
    url.searchParams.set("browser_approval_token", token);
  }
  return `${url.pathname}${url.search}${url.hash}`;
}

function sameOriginRelativePath(pathOrUrl: string): string {
  const normalized = pathOrUrl.trim();
  if (!normalized) return "";
  const url = sameOriginUrl(normalized);
  return url ? `${url.pathname}${url.search}${url.hash}` : "";
}

function sameOriginUrl(pathOrUrl: string): URL | null {
  try {
    const hasWindow = typeof window !== "undefined";
    const relativeSameOriginPath = pathOrUrl.startsWith("/") && !pathOrUrl.startsWith("//");

    // Outside a browser there is no authoritative application origin. Keep
    // tests and server-side rendering fail-closed by accepting only an
    // unambiguous root-relative path.
    if (!hasWindow && !relativeSameOriginPath) return null;

    const base = hasWindow ? window.location.origin : "http://127.0.0.1";
    const url = new URL(pathOrUrl, base);

    if (hasWindow && url.origin !== window.location.origin) return null;
    if (!hasWindow && !relativeSameOriginPath) return null;
    return url;
  } catch {
    return null;
  }
}

function locationSearch(): string {
  try {
    return typeof window === "undefined" ? "" : window.location.search;
  } catch {
    return "";
  }
}

function readStorageValue(kind: "sessionStorage"): string {
  try {
    return window[kind].getItem(BROWSER_APPROVAL_TOKEN_STORAGE_KEY)?.trim() ?? "";
  } catch {
    return "";
  }
}

function writeStorageValue(kind: "sessionStorage", value: string): void {
  try {
    if (value) window[kind].setItem(BROWSER_APPROVAL_TOKEN_STORAGE_KEY, value);
    else window[kind].removeItem(BROWSER_APPROVAL_TOKEN_STORAGE_KEY);
  } catch {
    // Browser storage may be unavailable in restricted webviews or private contexts.
  }
}

function removeStorageValue(kind: "sessionStorage" | "localStorage"): void {
  try {
    window[kind].removeItem(BROWSER_APPROVAL_TOKEN_STORAGE_KEY);
  } catch {
    // Browser storage may be unavailable in restricted webviews or private contexts.
  }
}
