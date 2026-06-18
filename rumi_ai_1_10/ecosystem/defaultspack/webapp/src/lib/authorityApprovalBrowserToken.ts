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

export function browserAuthorityApprovalPath(requestId: string, browserApprovalToken: string): string {
  const params = new URLSearchParams();
  params.set("request_id", requestId);
  const token = browserApprovalToken.trim();
  if (token) params.set("browser_approval_token", token);
  return `/approval?${params.toString()}`;
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
