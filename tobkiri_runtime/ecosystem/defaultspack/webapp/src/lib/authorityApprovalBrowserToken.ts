/**
 * Legacy browser approval credential cleanup and safe approval navigation.
 *
 * Approval credentials must never be returned from this module. The legacy name is
 * retained temporarily so older imports cannot accidentally restore credential
 * transport while clients are migrated.
 */

export const BROWSER_APPROVAL_TOKEN_STORAGE_KEY = "rumi.authority.browserApprovalToken";

export const LEGACY_BROWSER_APPROVAL_PARAM_KEYS = [
  "browser_approval_token",
  "approval_browser_token",
  "browserApprovalToken",
] as const;

const LEGACY_BROWSER_APPROVAL_STORAGE_KEYS = [
  BROWSER_APPROVAL_TOKEN_STORAGE_KEY,
  ...LEGACY_BROWSER_APPROVAL_PARAM_KEYS,
] as const;

export type LegacyApprovalCleanupResult = {
  cleanedPath: string;
  changed: boolean;
  rejected: boolean;
};

/** Return an origin-relative path only when the target is unambiguously same-origin. */
export function safeSameOriginApprovalPath(
  pathOrUrl: string,
  origin = currentOrigin(),
): string | null {
  const candidate = pathOrUrl.trim();
  if (
    !candidate
    || !origin
    || /[\\\u0000-\u001f\u007f]/.test(candidate)
    || candidate.startsWith("//")
  ) {
    return null;
  }
  try {
    const parsedOrigin = new URL(origin);
    const target = new URL(candidate, parsedOrigin);
    if (target.origin !== parsedOrigin.origin) return null;
    if (target.protocol !== "http:" && target.protocol !== "https:") return null;
    if (target.username || target.password || containsLegacyApprovalCredential(target)) return null;
    return `${target.pathname}${target.search}${target.hash}`;
  } catch {
    return null;
  }
}

/** Build a credential-free approval route. Unsafe return targets are omitted. */
export function browserAuthorityApprovalPath(requestId: string, returnTo = ""): string {
  const params = new URLSearchParams();
  params.set("request_id", requestId.trim());
  if (returnTo.trim()) {
    const safeReturnTo = safeSameOriginApprovalPath(returnTo);
    if (safeReturnTo) params.set("return_to", safeReturnTo);
  }
  return `/approval?${params.toString()}`;
}

/**
 * Compatibility wrapper for old call sites. It validates the destination and never
 * reads, accepts, or appends a credential.
 */
export function browserApprovalTokenizedPath(pathOrUrl: string): string | null {
  return safeSameOriginApprovalPath(pathOrUrl);
}

/** Remove legacy credential aliases from a same-origin URL without exposing values. */
export function scrubLegacyApprovalUrl(
  urlLike: string,
  origin = currentOrigin(),
): LegacyApprovalCleanupResult {
  if (!origin || /[\\\u0000-\u001f\u007f]/.test(urlLike) || urlLike.startsWith("//")) {
    return { cleanedPath: "/", changed: false, rejected: true };
  }
  try {
    const parsedOrigin = new URL(origin);
    const url = new URL(urlLike, parsedOrigin);
    if (url.origin !== parsedOrigin.origin) {
      return { cleanedPath: "/", changed: false, rejected: true };
    }
    let changed = false;
    for (const key of LEGACY_BROWSER_APPROVAL_PARAM_KEYS) {
      if (url.searchParams.has(key)) {
        url.searchParams.delete(key);
        changed = true;
      }
    }
    const cleanedHash = scrubLegacyApprovalHash(url.hash);
    if (cleanedHash !== url.hash) {
      url.hash = cleanedHash;
      changed = true;
    }
    return {
      cleanedPath: `${url.pathname}${url.search}${url.hash}`,
      changed,
      rejected: false,
    };
  } catch {
    return { cleanedPath: "/", changed: false, rejected: true };
  }
}

/** Clear leaked URL/history/storage state synchronously, returning no credentials. */
export function cleanupLegacyApprovalCredentialsEarly(): boolean {
  if (typeof window === "undefined") return false;
  let foundLegacyState = clearLegacyApprovalStorage();
  try {
    const result = scrubLegacyApprovalUrl(window.location.href, window.location.origin);
    foundLegacyState = foundLegacyState || result.changed;
    if (result.changed) {
      window.history.replaceState(window.history.state, "", result.cleanedPath);
    }
  } catch {
    // A restricted webview may deny location/history access; storage was still cleared.
  }
  return foundLegacyState;
}

function currentOrigin(): string {
  try {
    return typeof window === "undefined" ? "http://127.0.0.1" : window.location.origin;
  } catch {
    return "";
  }
}

function clearLegacyApprovalStorage(): boolean {
  let found = false;
  for (const kind of ["sessionStorage", "localStorage"] as const) {
    try {
      const storage = window[kind];
      for (const key of LEGACY_BROWSER_APPROVAL_STORAGE_KEYS) {
        if (storage.getItem(key) !== null) found = true;
        storage.removeItem(key);
      }
    } catch {
      // Browser storage may be unavailable in restricted webviews/private contexts.
    }
  }
  return found;
}

function scrubLegacyApprovalHash(hash: string): string {
  if (!hash) return hash;
  const raw = hash.slice(1);
  const questionIndex = raw.indexOf("?");
  const prefix = questionIndex >= 0 ? raw.slice(0, questionIndex + 1) : "";
  const parameterText = questionIndex >= 0 ? raw.slice(questionIndex + 1) : raw;
  const params = new URLSearchParams(parameterText);
  let changed = false;
  for (const key of LEGACY_BROWSER_APPROVAL_PARAM_KEYS) {
    if (params.has(key)) {
      params.delete(key);
      changed = true;
    }
  }
  if (!changed) return hash;
  const remaining = params.toString();
  if (!remaining) return prefix && prefix !== "?" ? `#${prefix.slice(0, -1)}` : "";
  return `#${prefix}${remaining}`;
}

function containsLegacyApprovalCredential(url: URL): boolean {
  if (LEGACY_BROWSER_APPROVAL_PARAM_KEYS.some((key) => url.searchParams.has(key))) return true;
  if (!url.hash) return false;
  const raw = url.hash.slice(1);
  const parameterText = raw.includes("?") ? raw.slice(raw.indexOf("?") + 1) : raw;
  const params = new URLSearchParams(parameterText);
  return LEGACY_BROWSER_APPROVAL_PARAM_KEYS.some((key) => params.has(key));
}
