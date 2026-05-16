import type { DashboardData, Profile, Theme, VersionInfo } from './types';

export const THEME_OPTIONS = ['Rumi', 'Minimal', 'Standard', 'Rounded'] as const satisfies readonly Theme[];

export const AVATAR_OPTIONS = [
  'https://picsum.photos/seed/rumi-av1/128/128',
  'https://picsum.photos/seed/rumi-av2/128/128',
  'https://picsum.photos/seed/rumi-av3/128/128',
  'https://picsum.photos/seed/rumi-av4/128/128',
  'https://picsum.photos/seed/rumi-av5/128/128',
];

export const defaultDashboard: DashboardData = {
  kernelStatus: 'stopped',
  uptime: '--',
  activePacks: 0,
  registeredFlows: 0,
  activities: [],
};

export const defaultProfile: Profile = {
  avatar: AVATAR_OPTIONS[0],
  username: 'User',
  language: 'en',
  job: '',
  connected: false,
};

export const defaultVersion: VersionInfo = {
  app: 'v1.10.0',
  kernel: '--',
  python: '--',
  launcher: '--',
  docker: {
    installed: false,
    version: '',
    type: '',
  },
};
