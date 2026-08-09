export const panelRoutes = {
  home: '/',
  setup: '/setup',
  packs: '/packs',
  packDetail: (id: string) => `/packs/${id}`,
} as const;

export type PanelRouteKey = Exclude<keyof typeof panelRoutes, 'packDetail'>;

export type PanelRouteMeta = {
  path: string;
  titleKey: string;
  navKey?: string;
};

export const panelRouteMeta: Record<PanelRouteKey, PanelRouteMeta> = {
  home: { path: panelRoutes.home, titleKey: 'nav.home', navKey: 'nav.home' },
  setup: { path: panelRoutes.setup, titleKey: 'nav.setup' },
  packs: { path: panelRoutes.packs, titleKey: 'nav.packs', navKey: 'nav.packs' },
};

export const viewerNavGroups = [
  {
    id: 'workspace',
    labelKey: 'nav.group.workspace',
    routes: ['home', 'packs'] satisfies PanelRouteKey[],
  },
] as const;

export function panelRouteTitleKey(pathname: string): string {
  if (pathname === panelRoutes.packs || pathname.startsWith(`${panelRoutes.packs}/`)) {
    return panelRouteMeta.packs.titleKey;
  }

  const match = Object.values(panelRouteMeta).find((meta) => meta.path === pathname);
  return match?.titleKey ?? 'nav.unknown';
}
