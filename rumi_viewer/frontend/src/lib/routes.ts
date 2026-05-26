export const panelRoutes = {
  home: '/',
  setup: '/setup',
  packs: '/packs',
  packDetail: (id: string) => `/packs/${id}`,
  nodes: '/nodes',
  graphEditor: '/graphs',
  profileGraph: '/profile-graph',
  apiMap: '/api-map',
  profileWorkspace: '/profile-workspace',
  startup: '/startup',
  flows: '/flows',
  settings: '/settings',
} as const;

function withQuery(path: string, params: Record<string, string | null | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    const normalized = String(value || '').trim();
    if (normalized) {
      search.set(key, normalized);
    }
  });
  const query = search.toString();
  return query ? `${path}?${query}` : path;
}

export function profileGraphRoute(profileId?: string | null): string {
  return withQuery(panelRoutes.profileGraph, {profile: profileId});
}

export function apiMapRoute(options?: {profileId?: string | null; focus?: string | null}): string {
  return withQuery(panelRoutes.apiMap, {
    profile_id: options?.profileId,
    focus: options?.focus,
  });
}
