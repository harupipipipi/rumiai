/** Canonical browser entry points owned by the Defaults frontend host. */

export const PACK_V4_CONVERSATION_ROUTE = "/pack-v4/conversation";

/** Remove only trailing path separators from a browser pathname. */
export function normalizeFrontendRoute(pathname: string): string {
  const normalized = pathname.trim().replace(/\/+$/, "");
  return normalized || "/";
}

/** Return whether a pathname selects the isolated Pack v4 conversation host. */
export function isPackV4ConversationRoute(pathname: string): boolean {
  return normalizeFrontendRoute(pathname) === PACK_V4_CONVERSATION_ROUTE;
}
