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
