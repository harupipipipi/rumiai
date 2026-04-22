export const panelRoutes = {
  home: '/',
  setup: '/setup',
  packs: '/packs',
  packDetail: (id: string) => `/packs/${id}`,
  flows: '/flows',
  settings: '/settings',
} as const;
