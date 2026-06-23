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
  try {
    const hasWindow = typeof window !== "undefined";
    const base = hasWindow ? window.location.origin : "http://127.0.0.1";
    const url = new URL(pathOrUrl, base);
    const hash = url.hash.startsWith("#") ? url.hash.slice(1) : url.hash;
    const params = new URLSearchParams(hash);
    if (!params.get(DEFAULTSPACK_LOCAL_AUTH_FRAGMENT_KEY)?.trim()) {
      params.set(DEFAULTSPACK_LOCAL_AUTH_FRAGMENT_KEY, localToken);
    }
    url.hash = params.toString();
    if (hasWindow && url.origin === window.location.origin) {
      return `${url.pathname}${url.search}${url.hash}`;
    }
    return url.toString();
  } catch {
    const separator = pathOrUrl.includes("#") ? "&" : "#";
    return `${pathOrUrl}${separator}${DEFAULTSPACK_LOCAL_AUTH_FRAGMENT_KEY}=${encodeURIComponent(localToken)}`;
  }
}

export function defaultspackUrlWithStoredLocalAuth(pathOrUrl: string): string {
  return defaultspackUrlWithLocalAuthToken(pathOrUrl, readStoredDefaultspackLocalAuthToken());
}
