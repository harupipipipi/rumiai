export type RouteCandidate = {
  url: string;
  final_url?: string;
  title?: string;
  snippet?: string;
  domain?: string;
  source?: string;
  status?: number | null;
  canonical_url?: string;
  content_type?: string;
  redirected?: boolean;
  looks_like_login?: boolean;
  looks_like_paywall?: boolean;
  looks_like_404?: boolean;
  looks_like_ad_heavy?: boolean;
  is_search_results?: boolean;
  heuristic_score?: number | null;
  screenshot_path?: string;
};

export type RouteDecision = {
  route_type?: string;
  query: string;
  target_url: string;
  target_candidates: RouteCandidate[];
  selected_index: number;
  fallback_url: string;
  resolution_reason?: string;
  used_ai_judge?: boolean;
  used_visual_judge?: boolean;
  metadata?: Record<string, unknown>;
};

export type RouteSessionCandidate = {
  url: string;
  final_url: string;
  title: string;
  domain: string;
};

export type RouteSessionState = {
  query: string;
  target_url: string;
  fallback_url: string;
  selected_index: number;
  target_candidates: RouteSessionCandidate[];
  updated_at: string;
};

export type RouteHotkeyAction = "next" | "prev" | "fallback";

export const ROUTE_SESSION_STORAGE_KEY = "rumi-search-home-route-state";
export const ROUTE_BROWSER_MESSAGE_TYPE = "rumi:search-home-route-state";

export function selectedCandidate(decision: RouteDecision, selectedIndex = decision.selected_index): RouteCandidate | null {
  if (!decision.target_candidates.length) {
    return null;
  }
  const normalizedIndex = normalizeSelectedIndex(decision, selectedIndex);
  return decision.target_candidates[normalizedIndex] ?? null;
}

export function selectedCandidateUrl(decision: RouteDecision, selectedIndex = decision.selected_index): string {
  const candidate = selectedCandidate(decision, selectedIndex);
  if (!candidate) {
    return decision.target_url || decision.fallback_url;
  }
  return candidate.final_url || candidate.url || decision.target_url || decision.fallback_url;
}

export function normalizeSelectedIndex(decision: RouteDecision, selectedIndex = decision.selected_index): number {
  const total = decision.target_candidates.length;
  if (total <= 0) {
    return -1;
  }
  if (!Number.isInteger(selectedIndex) || selectedIndex < 0 || selectedIndex >= total) {
    return 0;
  }
  return selectedIndex;
}

export function cycleCandidateIndex(decision: RouteDecision, currentIndex: number, delta: number): number {
  const total = decision.target_candidates.length;
  if (total <= 0) {
    return -1;
  }
  const start = normalizeSelectedIndex(decision, currentIndex);
  return (start + delta + total) % total;
}

export function routeHotkeyActionFromKeyboardEvent(eventLike: { altKey?: boolean; key?: string }): RouteHotkeyAction | null {
  if (!eventLike.altKey) {
    return null;
  }
  if (eventLike.key === "ArrowRight") {
    return "next";
  }
  if (eventLike.key === "ArrowLeft") {
    return "prev";
  }
  if (eventLike.key === "Enter") {
    return "fallback";
  }
  return null;
}

export function buildRouteSessionState(decision: RouteDecision, selectedIndex = decision.selected_index): RouteSessionState {
  const normalizedIndex = normalizeSelectedIndex(decision, selectedIndex);
  const candidates = decision.target_candidates.map((candidate) => ({
    url: candidate.url,
    final_url: candidate.final_url || candidate.url,
    title: candidate.title || "",
    domain: candidate.domain || "",
  }));
  return {
    query: decision.query,
    target_url: selectedCandidateUrl(decision, normalizedIndex),
    fallback_url: decision.fallback_url,
    selected_index: normalizedIndex,
    target_candidates: candidates,
    updated_at: new Date().toISOString(),
  };
}

export function persistRouteSessionState(storage: Pick<Storage, "setItem"> | null | undefined, decision: RouteDecision, selectedIndex = decision.selected_index): RouteSessionState | null {
  if (!storage) {
    return null;
  }
  const state = buildRouteSessionState(decision, selectedIndex);
  storage.setItem(ROUTE_SESSION_STORAGE_KEY, JSON.stringify(state));
  return state;
}

export function buildBrowserCompanionRouteMessage(decision: RouteDecision, selectedIndex = decision.selected_index): { type: string; payload: RouteSessionState } {
  return {
    type: ROUTE_BROWSER_MESSAGE_TYPE,
    payload: buildRouteSessionState(decision, selectedIndex),
  };
}

export function routeNavigationForHotkey(decision: RouteDecision, currentIndex: number, action: RouteHotkeyAction): { url: string; nextIndex: number } | null {
  if (action === "fallback") {
    return {
      url: decision.fallback_url,
      nextIndex: normalizeSelectedIndex(decision, currentIndex),
    };
  }
  const delta = action === "next" ? 1 : -1;
  const nextIndex = cycleCandidateIndex(decision, currentIndex, delta);
  if (nextIndex < 0) {
    return null;
  }
  return {
    url: selectedCandidateUrl(decision, nextIndex),
    nextIndex,
  };
}
