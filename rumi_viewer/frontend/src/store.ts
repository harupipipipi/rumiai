import { create } from 'zustand';
import {
  checkHealth,
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
  fetchUpdates,
  fetchUpdateSettings,
  updateUpdateSettings,
  applyUpdate as apiApplyUpdate,
  openExternalUrl,
  startOAuth,
} from './lib/api';
import {
  transformDashboard,
  transformPacks,
  transformFlows,
  transformProfile,
  transformVersion,
} from './lib/transforms';
import { RUMI_DISPLAY_VERSION } from './lib/version';

export type Theme = 'Rumi' | 'Minimal' | 'Standard' | 'Rounded';
const VALID_THEMES: Theme[] = ['Rumi', 'Minimal', 'Standard', 'Rounded'];

export type ColorMode = 'light' | 'dark';

function readLocalStorage(key: string): string | null {
  try {
    if (typeof localStorage === 'undefined' || typeof localStorage.getItem !== 'function') {
      return null;
    }
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeLocalStorage(key: string, value: string): void {
  try {
    if (typeof localStorage === 'undefined' || typeof localStorage.setItem !== 'function') {
      return;
    }
    localStorage.setItem(key, value);
  } catch {
    // Ignore storage failures in non-browser contexts.
  }
}

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

export type UpdateTarget = 'rumiai' | 'defaultspack';

export interface UpdateInfo {
  target: UpdateTarget;
  currentVersion: string;
  latestVersion: string;
  updateAvailable: boolean;
  releaseUrl: string;
  repo: string;
}

export type RuntimeStatus = 'starting' | 'panel_ready' | 'runtime_ready' | 'error';

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

  runtimeReady: boolean;
  runtimeStatus: RuntimeStatus;
  runtimeError: string | null;
  setRuntimeHealth: (health: { status?: 'ok' | 'error'; panel_ready?: boolean; runtime_ready?: boolean; runtime_status?: RuntimeStatus; runtime_error?: string | null }) => void;
  refreshRuntimeHealth: () => Promise<void>;

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
  updates: UpdateInfo[];
  autoUpdate: Record<UpdateTarget, boolean>;
  updatesLoading: boolean;
  updateSettingsLoading: boolean;
  updateApplyingTarget: UpdateTarget | null;
  loadUpdates: () => Promise<void>;
  loadUpdateSettings: () => Promise<void>;
  setAutoUpdate: (target: UpdateTarget, enabled: boolean) => Promise<void>;
  applyUpdate: (target: UpdateTarget) => Promise<void>;
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
  app: RUMI_DISPLAY_VERSION,
  kernel: '--',
  python: '--',
  launcher: '--',
  docker: {
    installed: false,
    version: '',
    type: '',
  },
};

function transformUpdateInfo(update: {
  target: UpdateTarget;
  current_version: string;
  latest_version: string;
  update_available: boolean;
  release_url: string;
  repo: string;
}): UpdateInfo {
  return {
    target: update.target,
    currentVersion: update.current_version,
    latestVersion: update.latest_version,
    updateAvailable: update.update_available,
    releaseUrl: update.release_url,
    repo: update.repo,
  };
}

export const useAppStore = create<AppState>((set, get) => ({
  theme: (readLocalStorage('rumi-theme') as Theme) || 'Rumi',
  setTheme: (theme) => {
    writeLocalStorage('rumi-theme', theme);
    set({ theme });
  },

  colorMode: (readLocalStorage('rumi-color-mode') as ColorMode) || 'dark',
  setColorMode: (mode) => {
    writeLocalStorage('rumi-color-mode', mode);
    set({ colorMode: mode });
  },

  isSetupDone: readLocalStorage('rumi-setup') === 'true',
  setSetupDone: (done) => {
    writeLocalStorage('rumi-setup', String(done));
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

  runtimeReady: false,
  runtimeStatus: 'starting',
  runtimeError: null,
  setRuntimeHealth: (health) =>
    set((state) => ({
      runtimeReady: Boolean(health.runtime_ready),
      runtimeStatus:
        health.runtime_status ??
        (health.status === 'error'
          ? 'error'
          : health.runtime_ready
            ? 'runtime_ready'
            : health.panel_ready
              ? 'panel_ready'
              : state.runtimeStatus),
      runtimeError: health.runtime_error ?? null,
    })),
  refreshRuntimeHealth: async () => {
    try {
      const health = await checkHealth();
      get().setRuntimeHealth(health);
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to read runtime health';
      get().setRuntimeHealth({
        status: 'error',
        runtime_status: 'error',
        runtime_error: msg,
      });
    }
  },

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
      await openExternalUrl(data.authorize_url);
    } catch (e) {
      throw e;
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

  updates: [],
  autoUpdate: { rumiai: false, defaultspack: false },
  updatesLoading: false,
  updateSettingsLoading: false,
  updateApplyingTarget: null,

  loadUpdates: async () => {
    set({ updatesLoading: true });
    try {
      const data = await fetchUpdates();
      set({ updates: data.updates.map(transformUpdateInfo), updatesLoading: false });
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to check updates';
      set({ updatesLoading: false });
      get().addToast(msg, 'error');
    }
  },

  loadUpdateSettings: async () => {
    set({ updateSettingsLoading: true });
    try {
      const data = await fetchUpdateSettings();
      set({ autoUpdate: data.auto_update, updateSettingsLoading: false });
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to load update settings';
      set({ updateSettingsLoading: false });
      get().addToast(msg, 'error');
    }
  },

  setAutoUpdate: async (target, enabled) => {
    const previous = get().autoUpdate;
    set({ autoUpdate: { ...previous, [target]: enabled }, updateSettingsLoading: true });
    try {
      const data = await updateUpdateSettings({ [target]: enabled });
      set({ autoUpdate: data.auto_update, updateSettingsLoading: false });
      get().addToast(`Auto update ${enabled ? 'enabled' : 'disabled'}: ${target}`, 'success');
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to save update settings';
      set({ autoUpdate: previous, updateSettingsLoading: false });
      get().addToast(msg, 'error');
    }
  },

  applyUpdate: async (target) => {
    set({ updateApplyingTarget: target });
    try {
      const result = await apiApplyUpdate(target);
      await get().loadUpdates();
      const suffix = result.restart_required
        ? ' Restart Rumi AI to finish.'
        : result.routes_reload_recommended
          ? ' Restart the Kernel to reload routes.'
          : '';
      get().addToast(`Update applied: ${target}.${suffix}`, 'success');
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to apply update';
      get().addToast(msg, 'error');
    } finally {
      set({ updateApplyingTarget: null });
    }
  },
}));
