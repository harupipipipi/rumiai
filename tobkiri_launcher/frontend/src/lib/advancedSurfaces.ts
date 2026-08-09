import type {RuntimeSurfaceId} from './runtimeSurface';

export type LauncherAdvancedViewId =
  | 'profile'
  | 'settings'
  | 'profileWiring'
  | 'profileFiles'
  | 'flow'
  | 'graph'
  | 'aiInput'
  | 'apiMap'
  | 'nodeManager';

export type LauncherViewSupport = 'rebuilt' | 'launcher_local' | 'mapped' | 'partial' | 'retired';

export interface LauncherAdvancedViewDescriptor {
  id: LauncherAdvancedViewId;
  label: string;
  support: LauncherViewSupport;
  sources: RuntimeSurfaceId[];
  summary: string;
  actions: 'local' | 'pack_lifecycle' | 'read_only' | 'none';
}

export const LAUNCHER_ADVANCED_VIEWS: Record<LauncherAdvancedViewId, LauncherAdvancedViewDescriptor> = {
  profile: {
    id: 'profile',
    label: 'Profile',
    support: 'rebuilt',
    sources: ['profile'],
    summary: 'Launcher-local preferences with a separate canonical runtime snapshot status.',
    actions: 'local',
  },
  settings: {
    id: 'settings',
    label: 'Settings',
    support: 'launcher_local',
    sources: ['settings'],
    summary: 'Theme, color mode, language, and avatar are presentation settings owned by Launcher.',
    actions: 'local',
  },
  profileWiring: {
    id: 'profileWiring',
    label: 'Profile Wiring',
    support: 'partial',
    sources: ['profile', 'principals', 'contracts'],
    summary: 'Read-only inspector reserved for exact ResolvedPlan bindings and Function principals.',
    actions: 'read_only',
  },
  profileFiles: {
    id: 'profileFiles',
    label: 'Profile Files',
    support: 'partial',
    sources: ['profile'],
    summary: 'Activation evidence and canonical record digests; no filesystem or profile-file browser.',
    actions: 'read_only',
  },
  flow: {
    id: 'flow',
    label: 'Flow',
    support: 'partial',
    sources: ['operations'],
    summary: 'Schema-driven Pack composition appears only when an exact Contract/Operation declares it.',
    actions: 'read_only',
  },
  graph: {
    id: 'graph',
    label: 'Graph',
    support: 'partial',
    sources: ['profile'],
    summary: 'Read-only Plan binding graph becomes available only with exact bindings from the v4 projection.',
    actions: 'read_only',
  },
  aiInput: {
    id: 'aiInput',
    label: 'AI Input',
    support: 'partial',
    sources: ['operations', 'contracts'],
    summary: 'Inputs are generated only from an exact operation schema and invokable snapshot binding.',
    actions: 'read_only',
  },
  apiMap: {
    id: 'apiMap',
    label: 'API & Route Map',
    support: 'partial',
    sources: ['contracts', 'operations', 'principals'],
    summary: 'Read-only map waits for exact generated route and Contract metadata.',
    actions: 'read_only',
  },
  nodeManager: {
    id: 'nodeManager',
    label: 'Node Manager',
    support: 'mapped',
    sources: ['packs'],
    summary: 'Pack and Pack lifecycle projection using the existing verified catalog actions.',
    actions: 'pack_lifecycle',
  },
};

export const ADVANCED_VIEW_ORDER: LauncherAdvancedViewId[] = [
  'profile',
  'settings',
  'profileWiring',
  'profileFiles',
  'flow',
  'graph',
  'aiInput',
  'apiMap',
  'nodeManager',
];
