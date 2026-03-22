import { create } from 'zustand';

export type Theme = 'Rumi' | 'Minimal' | 'Standard' | 'Rounded';
const VALID_THEMES: Theme[] = ['Rumi', 'Minimal', 'Standard', 'Rounded'];

export type ColorMode = 'light' | 'dark';

export const AVATAR_OPTIONS = [
  'https://picsum.photos/seed/rumi-av1/128/128',
  'https://picsum.photos/seed/rumi-av2/128/128',
  'https://picsum.photos/seed/rumi-av3/128/128',
  'https://picsum.photos/seed/rumi-av4/128/128',
  'https://picsum.photos/seed/rumi-av5/128/128',
];

export interface Toast {
  id: string;
  message: string;
  type: 'success' | 'error';
}

export interface DialogConfig {
  title: string;
  message: string;
  onConfirm: () => void;
  confirmText?: string;
  cancelText?: string;
}

export interface Pack {
  id: string;
  name: string;
  version: string;
  type: 'core' | 'community';
  enabled: boolean;
  description: string;
  capabilities: { name: string; description: string }[];
  flows: string[];
  dependencies: string[];
}

export interface Flow {
  id: string;
  name: string;
  content: string;
}

export interface Activity {
  id: number;
  timestamp: string;
  type: 'kernel_start' | 'pack_load' | 'flow_success' | 'flow_fail' | 'error';
  message: string;
}

export interface DashboardData {
  kernelStatus: 'running' | 'stopped' | 'error';
  uptime: string;
  activePacks: number;
  registeredFlows: number;
  activities: Activity[];
}

export interface Profile {
  avatar: string;
  username: string;
  language: string;
  job: string;
  connected: boolean;
}

export interface VersionInfo {
  app: string;
  kernel: string;
  python: string;
  launcher: string;
  docker: {
    installed: boolean;
    version: string;
    type: string;
  };
}

interface AppState {
  theme: Theme;
  setTheme: (theme: Theme) => void;

  colorMode: ColorMode;
  setColorMode: (mode: ColorMode) => void;

  isSetupDone: boolean;
  setSetupDone: (done: boolean) => void;

  isSidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;

  toasts: Toast[];
  addToast: (message: string, type: 'success' | 'error') => void;
  removeToast: (id: string) => void;

  dialog: DialogConfig | null;
  showDialog: (config: DialogConfig) => void;
  closeDialog: () => void;

  packs: Pack[];
  togglePack: (id: string) => void;

  flows: Flow[];
  addFlow: (flow: Flow) => void;
  updateFlow: (id: string, content: string) => void;
  deleteFlow: (id: string) => void;

  dashboard: DashboardData;
  setKernelStatus: (status: 'running' | 'stopped' | 'error') => void;

  profile: Profile;
  updateProfile: (profile: Partial<Profile>) => void;
  connectAccount: () => void;

  version: VersionInfo;
}

const initialPacks: Pack[] = [
  { id: 'core_setup', name: 'core_setup', version: 'v1.0.0', type: 'core', enabled: true, description: 'System setup utilities', capabilities: [{ name: 'fs_read', description: 'Read files' }], flows: ['00_startup'], dependencies: [] },
  { id: 'core_control_panel', name: 'core_control_panel', version: 'v1.1.0', type: 'core', enabled: true, description: 'Control panel UI backend', capabilities: [], flows: [], dependencies: ['core_setup'] },
  { id: 'core_communication', name: 'core_communication', version: 'v0.9.5', type: 'core', enabled: false, description: 'External API communication', capabilities: [{ name: 'network_access', description: 'Access internet' }], flows: [], dependencies: [] },
  { id: 'core_docker', name: 'core_docker', version: 'v2.0.1', type: 'community', enabled: true, description: 'Docker container management', capabilities: [{ name: 'docker_socket', description: 'Access Docker daemon' }], flows: ['setup_wizard'], dependencies: [] },
];

const initialFlows: Flow[] = [
  { id: '00_startup', name: '00_startup.yaml', content: 'steps:\n  - name: init\n    action: core_setup.init\n  - name: start_ui\n    action: core_control_panel.start' },
  { id: 'setup_wizard', name: 'setup_wizard.yaml', content: 'steps:\n  - name: check_docker\n    action: core_docker.check\n  - name: pull_image\n    action: core_docker.pull\n    args:\n      image: "ubuntu:latest"' },
];

const initialDashboard: DashboardData = {
  kernelStatus: 'running',
  uptime: '12h 34m',
  activePacks: 3,
  registeredFlows: 2,
  activities: [
    { id: 1, timestamp: '10:00', type: 'kernel_start', message: 'Kernel started successfully' },
    { id: 2, timestamp: '10:05', type: 'pack_load', message: 'Loaded core_setup' },
    { id: 3, timestamp: '10:06', type: 'flow_success', message: 'Flow 00_startup executed' },
    { id: 4, timestamp: '11:20', type: 'error', message: 'Failed to connect to Docker daemon' },
    { id: 5, timestamp: '11:25', type: 'flow_fail', message: 'Flow setup_wizard failed' },
    { id: 6, timestamp: '12:00', type: 'pack_load', message: 'Loaded core_docker' },
    { id: 7, timestamp: '12:15', type: 'flow_success', message: 'Flow setup_wizard retried and succeeded' },
    { id: 8, timestamp: '13:00', type: 'kernel_start', message: 'Kernel health check passed' },
  ],
};

const initialProfile: Profile = {
  avatar: AVATAR_OPTIONS[0],
  username: 'User',
  language: 'en',
  job: 'Developer',
  connected: false,
};

const initialVersion: VersionInfo = {
  app: 'v1.2.0',
  kernel: 'v0.8.5',
  python: '3.11.4',
  launcher: 'v2.0.1',
  docker: {
    installed: true,
    version: '24.0.5',
    type: 'Docker Desktop',
  },
};

export const useAppStore = create<AppState>((set) => ({
  theme: (localStorage.getItem('rumi-theme') as Theme) || 'Rumi',
  setTheme: (theme) => {
    localStorage.setItem('rumi-theme', theme);
    set({ theme });
  },

  colorMode: (localStorage.getItem('rumi-color-mode') as ColorMode) || 'dark',
  setColorMode: (mode) => {
    localStorage.setItem('rumi-color-mode', mode);
    set({ colorMode: mode });
  },

  isSetupDone: localStorage.getItem('rumi-setup') === 'true',
  setSetupDone: (done) => {
    localStorage.setItem('rumi-setup', String(done));
    set({ isSetupDone: done });
  },

  isSidebarOpen: true,
  setSidebarOpen: (open) => set({ isSidebarOpen: open }),

  toasts: [],
  addToast: (message, type) => {
    const id = Math.random().toString(36).substring(2, 9);
    set((state) => ({ toasts: [...state.toasts, { id, message, type }] }));
    setTimeout(() => {
      set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }));
    }, 3000);
  },
  removeToast: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),

  dialog: null,
  showDialog: (config) => set({ dialog: config }),
  closeDialog: () => set({ dialog: null }),

  packs: initialPacks,
  togglePack: (id) =>
    set((state) => {
      const newPacks = state.packs.map((p) => (p.id === id ? { ...p, enabled: !p.enabled } : p));
      return { packs: newPacks, dashboard: { ...state.dashboard, activePacks: newPacks.filter((p) => p.enabled).length } };
    }),

  flows: initialFlows,
  addFlow: (flow) =>
    set((state) => {
      const newFlows = [...state.flows, flow];
      return { flows: newFlows, dashboard: { ...state.dashboard, registeredFlows: newFlows.length } };
    }),
  updateFlow: (id, content) =>
    set((state) => ({
      flows: state.flows.map((f) => (f.id === id ? { ...f, content } : f)),
    })),
  deleteFlow: (id) =>
    set((state) => {
      const newFlows = state.flows.filter((f) => f.id !== id);
      return { flows: newFlows, dashboard: { ...state.dashboard, registeredFlows: newFlows.length } };
    }),

  dashboard: initialDashboard,
  setKernelStatus: (status) =>
    set((state) => ({
      dashboard: { ...state.dashboard, kernelStatus: status },
    })),

  profile: initialProfile,
  updateProfile: (profile) =>
    set((state) => ({
      profile: { ...state.profile, ...profile },
    })),
  connectAccount: () =>
    set((state) => ({
      profile: { ...state.profile, connected: true },
    })),

  version: initialVersion,
}));
