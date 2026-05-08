export const panelRoutes = {
  home: '/',
  setup: '/setup',
  packs: '/packs',
  packDetail: (id: string) => `/packs/${id}`,
  nodes: '/nodes',
  graphEditor: '/graphs',
  startup: '/startup',
  flows: '/flows',
  settings: '/settings',
} as const;
