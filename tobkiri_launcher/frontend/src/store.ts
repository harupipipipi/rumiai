import {create} from 'zustand';
import {
  approvePack as apiApprovePack,
  checkHealth,
  disablePack as apiDisablePack,
  enablePack as apiEnablePack,
  fetchPacks,
  installPack as apiInstallPack,
} from './lib/api';
import type {ApiSupervisorDashboard} from './lib/apiTypes';
import {transformPacks} from './lib/transforms';
import {
  COLOR_MODE_STORAGE_KEY,
  THEME_STORAGE_KEY,
  normalizeColorMode,
  normalizeTheme,
} from './lib/appearance';
import type {ColorMode, Theme} from './lib/appearance';
import {AVATAR_OPTIONS, DEFAULT_AVATAR} from './lib/avatar';

export type {ColorMode, Theme} from './lib/appearance';
export {AVATAR_OPTIONS} from './lib/avatar';

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

export interface Toast {
  id: string;
  message: string;
  type: 'success' | 'error';
}

export interface DialogConfig {
  title: string;
  message: string;
  onConfirm: () => void | Promise<void>;
  confirmText?: string;
  confirmPendingText?: string;
  cancelText?: string;
}

export interface Pack {
  id: string;
  name: string;
  version: string;
  type: 'core' | 'community';
  installed: boolean;
  enabled: boolean;
  description: string;
  artifactDigest: string;
  profileId: string;
  workspaceId: string;
  profileRevision: string;
  planDigest: string;
  catalogRevision: string;
  approvalStatus: string;
  approvalReason: string | null;
  approved: boolean;
  hashValid: boolean | null;
  criticalChanged: boolean | null;
  approvalIssues: string[];
  capabilities: {name: string; description: string}[];
  flows: string[];
  dependencies: string[];
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
  supervisor: ApiSupervisorDashboard | null;
}

export interface Profile {
  avatar: string;
  username: string;
  language: string;
  job: string;
  connected: boolean;
}

export type RuntimeStatus = 'starting' | 'panel_ready' | 'runtime_ready' | 'error';

const SIDEBAR_STORAGE_KEY = 'tobkiri-launcher-sidebar-open';
const LEGACY_SIDEBAR_STORAGE_KEY = 'rumi-viewer-sidebar-open';
const SETUP_STORAGE_KEY = 'tobkiri-launcher-setup';
const LEGACY_SETUP_STORAGE_KEY = 'rumi-setup';

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
  runtimeDisconnected: boolean;
  lastRuntimeHealthyAt: number | null;
  setRuntimeHealth: (health: {
    status?: 'ok' | 'error';
    panel_ready?: boolean;
    runtime_ready?: boolean;
    runtime_status?: RuntimeStatus;
    runtime_error?: string | null;
  }) => void;
  refreshRuntimeHealth: () => Promise<void>;
  packs: Pack[];
  packsLoading: boolean;
  packsError: string | null;
  packInstallPending: Record<string, boolean>;
  packTogglePending: Record<string, boolean>;
  loadPacks: () => Promise<void>;
  installPack: (id: string) => Promise<void>;
  approvePack: (id: string) => Promise<void>;
  togglePack: (id: string) => Promise<boolean>;
  profile: Profile;
}

const defaultProfile: Profile = {
  avatar: DEFAULT_AVATAR,
  username: 'User',
  language: 'en',
  job: '',
  connected: false,
};

let packsLoadPromise: Promise<void> | null = null;
const packMutationVersions = new Map<string, number>();

export const useAppStore = create<AppState>((set, get) => ({
  theme: normalizeTheme(readLocalStorage(THEME_STORAGE_KEY)),
  setTheme: (theme) => {
    writeLocalStorage(THEME_STORAGE_KEY, theme);
    set({theme});
  },

  colorMode: normalizeColorMode(readLocalStorage(COLOR_MODE_STORAGE_KEY)),
  setColorMode: (mode) => {
    writeLocalStorage(COLOR_MODE_STORAGE_KEY, mode);
    set({colorMode: mode});
  },

  isSetupDone:
    (readLocalStorage(SETUP_STORAGE_KEY) ?? readLocalStorage(LEGACY_SETUP_STORAGE_KEY)) === 'true',
  setSetupDone: (done) => {
    writeLocalStorage(SETUP_STORAGE_KEY, String(done));
    set({isSetupDone: done});
  },

  isSidebarOpen:
    (readLocalStorage(SIDEBAR_STORAGE_KEY) ?? readLocalStorage(LEGACY_SIDEBAR_STORAGE_KEY)) !== 'false',
  setSidebarOpen: (open) => {
    writeLocalStorage(SIDEBAR_STORAGE_KEY, String(open));
    set({isSidebarOpen: open});
  },

  toasts: [],
  addToast: (message, type) => {
    const id = Math.random().toString(36).substring(2, 9);
    set((state) => ({toasts: [...state.toasts, {id, message, type}]}));
    setTimeout(() => {
      set((state) => ({toasts: state.toasts.filter((toast) => toast.id !== id)}));
    }, 3000);
  },
  removeToast: (id) => set((state) => ({toasts: state.toasts.filter((toast) => toast.id !== id)})),

  dialog: null,
  showDialog: (config) => set({dialog: config}),
  closeDialog: () => set({dialog: null}),

  isLoading: false,
  apiError: null,

  runtimeReady: false,
  runtimeStatus: 'starting',
  runtimeError: null,
  runtimeDisconnected: false,
  lastRuntimeHealthyAt: null,
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
      runtimeDisconnected: false,
      lastRuntimeHealthyAt: health.runtime_ready ? Date.now() : state.lastRuntimeHealthyAt,
    })),
  refreshRuntimeHealth: async () => {
    try {
      const health = await checkHealth();
      get().setRuntimeHealth(health);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to read runtime health';
      set((state) => ({
        runtimeReady: false,
        runtimeStatus: 'error',
        runtimeError: message,
        runtimeDisconnected: state.lastRuntimeHealthyAt !== null,
      }));
    }
  },

  packs: [],
  packsLoading: false,
  packsError: null,
  packInstallPending: {},
  packTogglePending: {},

  loadPacks: () => {
    if (packsLoadPromise) return packsLoadPromise;
    const versionsAtStart = new Map(packMutationVersions);
    set({packsLoading: true, packsError: null});
    packsLoadPromise = (async () => {
      try {
        const data = await fetchPacks();
        const latestState = get();
        const currentById = new Map(latestState.packs.map((pack) => [pack.id, pack]));
        const packs = transformPacks(data.packs).map((pack) => {
          const before = versionsAtStart.get(pack.id) ?? 0;
          const after = packMutationVersions.get(pack.id) ?? 0;
          if (before === after && !latestState.packTogglePending[pack.id]) return pack;
          const current = currentById.get(pack.id);
          return current ? {...pack, enabled: current.enabled} : pack;
        });
        set({packs, packsError: null});
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Failed to load packs';
        set({packsError: message});
        get().addToast(message, 'error');
      }
    })().finally(() => {
      packsLoadPromise = null;
      set({packsLoading: false});
    });
    return packsLoadPromise;
  },

  installPack: async (id) => {
    const state = get();
    if (state.packInstallPending[id]) return;
    set((current) => ({packInstallPending: {...current.packInstallPending, [id]: true}}));
    try {
      await apiInstallPack(id);
      await get().loadPacks();
      get().addToast('Pack installed.', 'success');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to install pack';
      get().addToast(message, 'error');
      throw error;
    } finally {
      set((current) => {
        const pending = {...current.packInstallPending};
        delete pending[id];
        return {packInstallPending: pending};
      });
    }
  },

  approvePack: async (id) => {
    try {
      await apiApprovePack(id);
      await get().loadPacks();
      get().addToast('Pack approved.', 'success');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to approve pack';
      get().addToast(message, 'error');
      throw error;
    }
  },

  togglePack: async (id) => {
    const state = get();
    const pack = state.packs.find((candidate) => candidate.id === id);
    if (!pack || state.packTogglePending[id]) return false;

    const version = (packMutationVersions.get(id) ?? 0) + 1;
    packMutationVersions.set(id, version);
    set((current) => ({
      packs: current.packs.map((candidate) => (
        candidate.id === id ? {...candidate, enabled: !pack.enabled} : candidate
      )),
      packTogglePending: {...current.packTogglePending, [id]: true},
    }));

    try {
      const response = pack.enabled
        ? await apiDisablePack(id)
        : await apiEnablePack(id);
      if (packMutationVersions.get(id) === version) {
        set((current) => ({
          packs: current.packs.map((candidate) => (
            candidate.id === id ? {...candidate, enabled: response.enabled} : candidate
          )),
        }));
      }
      return true;
    } catch (error) {
      if (packMutationVersions.get(id) === version) {
        set((current) => ({
          packs: current.packs.map((candidate) => (
            candidate.id === id ? {...candidate, enabled: pack.enabled} : candidate
          )),
        }));
      }
      const message = error instanceof Error ? error.message : 'Failed to toggle pack';
      get().addToast(message, 'error');
      return false;
    } finally {
      set((current) => {
        const pending = {...current.packTogglePending};
        delete pending[id];
        return {packTogglePending: pending};
      });
    }
  },

  profile: defaultProfile,
}));
