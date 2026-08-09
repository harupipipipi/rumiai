import {lazy, type ComponentType, type LazyExoticComponent} from 'react';

import type {PanelRouteKey} from './routes';

export type RouteModuleKey =
  | 'packs'
  | 'packDetail';

type RouteModuleLoader = () => Promise<unknown>;

const rawRouteModuleLoaders: Record<RouteModuleKey, RouteModuleLoader> = {
  packs: () => import('../pages/Packs'),
  packDetail: () => import('../pages/PackDetail'),
};

export const routeModuleSources: Record<RouteModuleKey, string> = {
  packs: 'src/pages/Packs.tsx',
  packDetail: 'src/pages/PackDetail.tsx',
};

const routeModulePromises = new Map<RouteModuleKey, Promise<unknown>>();

export function preloadRouteModule(key: RouteModuleKey): Promise<unknown> {
  const existing = routeModulePromises.get(key);
  if (existing) return existing;

  const promise = rawRouteModuleLoaders[key]().catch((error) => {
    routeModulePromises.delete(key);
    throw error;
  });
  routeModulePromises.set(key, promise);
  return promise;
}

const panelRouteToModule: Partial<Record<PanelRouteKey, RouteModuleKey>> = {
  packs: 'packs',
};

export function preloadPanelRoute(route: PanelRouteKey): Promise<unknown> | null {
  const key = panelRouteToModule[route];
  return key ? preloadRouteModule(key) : null;
}

function lazyNamedRoute(
  key: RouteModuleKey,
  exportName: string,
): LazyExoticComponent<ComponentType> {
  return lazy(async () => {
    const routeModule = await preloadRouteModule(key) as Record<string, unknown>;
    const component = routeModule[exportName];
    if (!component || (typeof component !== 'function' && typeof component !== 'object')) {
      throw new Error(`Route module ${key} did not export ${exportName}`);
    }
    return {default: component as ComponentType};
  });
}

export const LazyPacks = lazyNamedRoute('packs', 'Packs');
export const LazyPackDetail = lazyNamedRoute('packDetail', 'PackDetail');
