export const PANEL_BASENAME = '/panel';

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

export type PanelChildRouteKey =
  | 'dashboard'
  | 'packs'
  | 'nodes'
  | 'graphEditor'
  | 'startup'
  | 'flows'
  | 'settings';

export interface PanelChildRoute {
  key: PanelChildRouteKey;
  path: string;
  index?: boolean;
}

export function toPanelChildRoutePath(route: string): string {
  return route === panelRoutes.home ? '' : route.replace(/^\//, '');
}

export const panelChildRoutes = [
  { key: 'dashboard', path: toPanelChildRoutePath(panelRoutes.home), index: true },
  { key: 'packs', path: toPanelChildRoutePath(panelRoutes.packs), index: false },
  { key: 'nodes', path: toPanelChildRoutePath(panelRoutes.nodes), index: false },
  { key: 'graphEditor', path: toPanelChildRoutePath(panelRoutes.graphEditor), index: false },
  { key: 'startup', path: toPanelChildRoutePath(panelRoutes.startup), index: false },
  { key: 'flows', path: toPanelChildRoutePath(panelRoutes.flows), index: false },
  { key: 'settings', path: toPanelChildRoutePath(panelRoutes.settings), index: false },
] as const satisfies readonly PanelChildRoute[];

export const panelPackDetailRoute = {
  key: 'packDetail',
  path: `${toPanelChildRoutePath(panelRoutes.packs)}/:id`,
} as const;
