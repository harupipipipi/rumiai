import { create } from 'zustand';
import {
  fetchDashboard,
  fetchPacks,
  fetchFlows,
  fetchProfile,
  fetchVersion,
  enablePack as apiEnablePack,
  disablePack as apiDisablePack,
  createFlow as apiCreateFlow,
  updateFlow as apiUpdateFlow,
  deleteFlow as apiDeleteFlow,
  updateProfile as apiUpdateProfile,
  restartKernel as apiRestartKernel,
  startOAuth,
} from './lib/api';
import {
  transformDashboard,
  transformPacks,
  transformFlows,
  transformProfile,
  transformVersion,
} from './lib/transforms';

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

  isLoading: boolean;
  apiError: string | null;

  packs: Pack[];
  loadPacks: () => Promise<void>;
  togglePack: (id: string) => Promise<void>;

  flows: Flow[];
  loadFlows: () => Promise<void>;
  addFlow: (flow: { id: string; name: string; content: string }) => Promise<void>;
  updateFlow: (id: string, content: string) => Promise<void>;
  deleteFlow: (id: string) => Promise<void>;

  dashboard: DashboardData;
  loadDashboard: () => Promise<void>;
  setKernelStatus: (status: 'running' | 'stopped' | 'error') => void;
  restartKernel: () => Promise<void>;

  profile: Profile;
  loadProfile: () => Promise<void>;
  updateProfile: (profile: Partial<Profile>) => Promise<void>;
  connectAccount: () => Promise<void>;

  version: VersionInfo;
  loadVersion: () => Promise<void>;
}

const defaultDashboard: DashboardData = {
  kernelStatus: 'stopped',
  uptime: '--',
  activePacks: 0,
  registeredFlows: 0,
  activities: [],
};

const defaultProfile: Profile = {
  avatar: AVATAR_OPTIONS[0],
  username: 'User',
  language: 'en',
  job: '',
  connected: false,
};

const defaultVersion: VersionInfo = {
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

export const useAppStore = create<AppState>((set, get) => ({
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

  isLoading: false,
  apiError: null,

  // ============================================================
  // Packs
  // ============================================================

  packs: [],

  loadPacks: async () => {
    set({ isLoading: true, apiError: null });
    try {
      const data = await fetchPacks();
      set({ packs: transformPacks(data.packs), isLoading: false });
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to load packs';
      set({ apiError: msg, isLoading: false });
      get().addToast(msg, 'error');
    }
  },

  togglePack: async (id) => {
    const pack = get().packs.find((p) => p.id === id);
    if (!pack) return;
    try {
      if (pack.enabled) {
        await apiDisablePack(id);
      } else {
        await apiEnablePack(id);
      }
      await get().loadPacks();
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to toggle pack';
      get().addToast(msg, 'error');
    }
  },

  // ============================================================
  // Flows
  // ============================================================

  flows: [],

  loadFlows: async () => {
    set({ isLoading: true, apiError: null });
    try {
      const data = await fetchFlows();
      set({ flows: transformFlows(data.flows), isLoading: false });
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to load flows';
      set({ apiError: msg, isLoading: false });
      get().addToast(msg, 'error');
    }
  },

  addFlow: async (flow) => {
    try {
      await apiCreateFlow({
        flow_id: flow.id,
        yaml_content: flow.content,
        filename: flow.name,
      });
      await get().loadFlows();
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to create flow';
      get().addToast(msg, 'error');
    }
  },

  updateFlow: async (id, content) => {
    try {
      await apiUpdateFlow(id, { yaml_content: content });
      await get().loadFlows();
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to update flow';
      get().addToast(msg, 'error');
    }
  },

  deleteFlow: async (id) => {
    try {
      await apiDeleteFlow(id);
      await get().loadFlows();
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to delete flow';
      get().addToast(msg, 'error');
    }
  },

  // ============================================================
  // Dashboard
  // ============================================================

  dashboard: defaultDashboard,

  loadDashboard: async () => {
    set({ isLoading: true, apiError: null });
    try {
      const data = await fetchDashboard();
      set({ dashboard: transformDashboard(data), isLoading: false });
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to load dashboard';
      set({ apiError: msg, isLoading: false });
      get().addToast(msg, 'error');
    }
  },

  setKernelStatus: (status) =>
    set((state) => ({
      dashboard: { ...state.dashboard, kernelStatus: status },
    })),

  restartKernel: async () => {
    try {
      await apiRestartKernel();
      set((state) => ({
        dashboard: { ...state.dashboard, kernelStatus: 'stopped' },
      }));
      setTimeout(() => {
        get().loadDashboard();
      }, 3000);
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to restart kernel';
      get().addToast(msg, 'error');
    }
  },

  // ============================================================
  // Profile
  // ============================================================

  profile: defaultProfile,

  loadProfile: async () => {
    try {
      const data = await fetchProfile();
      set({ profile: transformProfile(data.profile) });
    } catch (e) {
      // Profile not found (404) is expected for new users
      const msg = e instanceof Error ? e.message : '';
      if (!msg.includes('Profile not found')) {
        set({ apiError: msg });
      }
    }
  },

  updateProfile: async (profileUpdate) => {
    try {
      const current = get().profile;
      const payload: Record<string, unknown> = {
        username: profileUpdate.username ?? current.username,
        language: profileUpdate.language ?? current.language,
        icon: profileUpdate.avatar ?? current.avatar,
        occupation: profileUpdate.job ?? current.job,
      };
      await apiUpdateProfile(payload);
      await get().loadProfile();
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to update profile';
      get().addToast(msg, 'error');
    }
  },

  connectAccount: async () => {
    try {
      const data = await startOAuth();
      window.location.href = data.authorize_url;
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to start OAuth';
      get().addToast(msg, 'error');
    }
  },

  // ============================================================
  // Version
  // ============================================================

  version: defaultVersion,

  loadVersion: async () => {
    try {
      const data = await fetchVersion();
      set({ version: transformVersion(data) });
    } catch (e) {
      // Version fetch failure is non-critical
      const msg = e instanceof Error ? e.message : 'Failed to load version';
      console.warn('Version fetch failed:', msg);
    }
  },
}));
