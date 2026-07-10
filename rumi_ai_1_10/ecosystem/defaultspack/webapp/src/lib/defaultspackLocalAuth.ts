const DEFAULTSPACK_LOCAL_AUTH_STORAGE_KEY = "rumi-defaultspack-local-auth";
const DEFAULTSPACK_LOCAL_AUTH_FRAGMENT_KEY = "rumi_local_auth";

function sessionStorageOrNull(): Storage | null {
  try {
    return typeof sessionStorage !== "undefined" ? sessionStorage : null;
  } catch {
    return null;
  }
}

export function readStoredDefaultspackLocalAuthToken(): string {
  return sessionStorageOrNull()?.getItem(DEFAULTSPACK_LOCAL_AUTH_STORAGE_KEY)?.trim() ?? "";
}

export function defaultspackUrlWithLocalAuthToken(pathOrUrl: string, token: string): string {
  const localToken = token.trim();
  if (!localToken) return pathOrUrl;

  // This is a temporary compatibility path. Never add reusable auth material
  // until the destination has been parsed and proven to be an unambiguous
  // same-origin HTTP(S) URL. The long-term fix tracked by #1071 removes the
  // credential from URLs entirely.
  const url = sameOriginHttpUrl(pathOrUrl);
  if (!url) return pathOrUrl;

  const hash = url.hash.startsWith("#") ? url.hash.slice(1) : url.hash;
  const params = new URLSearchParams(hash);
  if (!params.get(DEFAULTSPACK_LOCAL_AUTH_FRAGMENT_KEY)?.trim()) {
    params.set(DEFAULTSPACK_LOCAL_AUTH_FRAGMENT_KEY, localToken);
  }
  url.hash = params.toString();
  return `${url.pathname}${url.search}${url.hash}`;
}

export function defaultspackUrlWithStoredLocalAuth(pathOrUrl: string): string {
  return defaultspackUrlWithLocalAuthToken(pathOrUrl, readStoredDefaultspackLocalAuthToken());
}

function sameOriginHttpUrl(pathOrUrl: string): URL | null {
  const normalized = pathOrUrl.trim();
  if (!normalized || normalized.startsWith("//")) return null;
  if (/[\u0000-\u001f\u007f]/.test(normalized)) return null;

  try {
    const hasWindow = typeof window !== "undefined";
    const rootRelativePath = normalized.startsWith("/") && !normalized.startsWith("//");

    // Outside a browser there is no authoritative application origin. Keep
    // SSR, tooling, and tests fail-closed by accepting only root-relative URLs.
    if (!hasWindow && !rootRelativePath) return null;

    const base = hasWindow ? window.location.origin : "http://127.0.0.1";
    const url = new URL(normalized, base);

    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    if (url.username || url.password) return null;
    if (hasWindow && url.origin !== window.location.origin) return null;
    if (!hasWindow && !rootRelativePath) return null;
    return url;
  } catch {
    return null;
  }
}
