import { create } from 'zustand';
import {
  checkHealth,
  fetchDashboard,
  fetchPacks,
  fetchFlows,
  fetchFlowDetail,
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
import type { ApiSupervisorDashboard } from './lib/apiTypes';
import {
  transformDashboard,
  transformPacks,
  transformFlows,
  transformProfile,
  transformVersion,
} from './lib/transforms';
import { RUMI_DISPLAY_VERSION } from './lib/version';
import {
  COLOR_MODE_STORAGE_KEY,
  THEME_STORAGE_KEY,
  normalizeColorMode,
  normalizeTheme,
} from './lib/appearance';
import type { ColorMode, Theme } from './lib/appearance';
import type { MutationResult } from './lib/mutations';

export type { ColorMode, Theme } from './lib/appearance';

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
  approvalStatus: string;
  approvalReason: string | null;
  approved: boolean;
  hashValid: boolean | null;
  criticalChanged: boolean | null;
  approvalIssues: string[];
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
  supervisor: ApiSupervisorDashboard | null;
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
  runtimeDisconnected: boolean;
  lastRuntimeHealthyAt: number | null;
  setRuntimeHealth: (health: { status?: 'ok' | 'error'; panel_ready?: boolean; runtime_ready?: boolean; runtime_status?: RuntimeStatus; runtime_error?: string | null }) => void;
  refreshRuntimeHealth: () => Promise<void>;

  packs: Pack[];
  pendingPackIds: string[];
  loadPacks: () => Promise<void>;
  togglePack: (id: string) => Promise<MutationResult>;

  flows: Flow[];
  loadFlows: () => Promise<void>;
  addFlow: (flow: { id: string; name: string; content: string }) => Promise<MutationResult>;
  updateFlow: (id: string, content: string) => Promise<MutationResult>;
  deleteFlow: (id: string) => Promise<MutationResult>;

  dashboard: DashboardData;
  loadDashboard: () => Promise<void>;
  setKernelStatus: (status: 'running' | 'stopped' | 'error') => void;
  restartKernel: () => Promise<void>;

  profile: Profile;
  loadProfile: () => Promise<void>;
  updateProfile: (profile: Partial<Profile>) => Promise<MutationResult>;
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
  supervisor: null,
};

const defaultProfile: Profile = {
  avatar: AVATAR_OPTIONS[0],
  username: 'User',
  language: 'en',
  job: '',
  connected: false,
};

const allowedProfileLanguages = new Set([
  'ja', 'en', 'zh', 'ko', 'es', 'fr', 'de', 'pt', 'ru', 'ar',
]);

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

// A pack write is not confirmed until its following list refresh completes.
// Keep that whole transaction serial so a later write cannot share an older
// in-flight GET through apiFetch's read deduplication.
let packMutationQueue: Promise<void> = Promise.resolve();
let packReadGeneration = 0;
let flowReadGeneration = 0;
let profileReadGeneration = 0;

function enqueuePackMutation(
  mutation: () => Promise<MutationResult>,
): Promise<MutationResult> {
  const result = packMutationQueue.then(mutation);
  packMutationQueue = result.then(
    () => undefined,
    () => undefined,
  );
  return result;
}

export const useAppStore = create<AppState>((set, get) => ({
  theme: normalizeTheme(readLocalStorage(THEME_STORAGE_KEY)),
  setTheme: (theme) => {
    writeLocalStorage(THEME_STORAGE_KEY, theme);
    set({ theme });
  },

  colorMode: normalizeColorMode(readLocalStorage(COLOR_MODE_STORAGE_KEY)),
  setColorMode: (mode) => {
    writeLocalStorage(COLOR_MODE_STORAGE_KEY, mode);
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
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to read runtime health';
      set((state) => ({
        runtimeReady: false,
        runtimeStatus: 'error',
        runtimeError: msg,
        runtimeDisconnected: state.lastRuntimeHealthyAt !== null,
      }));
    }
  },

  // ============================================================
  // Packs
  // ============================================================

  packs: [],
  pendingPackIds: [],

  loadPacks: async () => {
    const readGeneration = packReadGeneration;
    set({ isLoading: true, apiError: null });
    try {
      const data = await fetchPacks();
      if (readGeneration !== packReadGeneration) {
        set({ isLoading: false });
        return;
      }
      set({ packs: transformPacks(data.packs), isLoading: false });
    } catch (e) {
      if (readGeneration !== packReadGeneration) {
        set({ isLoading: false });
        return;
      }
      const msg = e instanceof Error ? e.message : 'Failed to load packs';
      set({ apiError: msg, isLoading: false });
      get().addToast(msg, 'error');
    }
  },

  togglePack: (id) => {
    const state = get();
    if (state.pendingPackIds.includes(id)) {
      return Promise.resolve({ok: false, error: 'Pack update already in progress'});
    }
    const pack = state.packs.find((candidate) => candidate.id === id);
    if (!pack) {
      const error = 'Pack not found';
      get().addToast(error, 'error');
      return Promise.resolve({ok: false, error});
    }

    const targetEnabled = !pack.enabled;
    packReadGeneration += 1;
    set((current) => ({
      pendingPackIds: current.pendingPackIds.concat(id),
    }));

    return enqueuePackMutation(async () => {
      try {
        if (targetEnabled) {
          await apiEnablePack(id);
        } else {
          await apiDisablePack(id);
        }
        const data = await fetchPacks({fresh: true});
        const confirmedPacks = transformPacks(data.packs);
        set({ packs: confirmedPacks });
        const confirmedPack = confirmedPacks.find((candidate) => candidate.id === id);
        if (!confirmedPack || confirmedPack.enabled !== targetEnabled) {
          throw new Error('Pack update was not confirmed');
        }
        return { ok: true };
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'Failed to toggle pack';
        get().addToast(msg, 'error');
        return { ok: false, error: msg };
      } finally {
        packReadGeneration += 1;
        set((current) => ({
          pendingPackIds: current.pendingPackIds.filter((packId) => packId !== id),
        }));
      }
    });
  },

  // ============================================================
  // Flows
  // ============================================================

  flows: [],

  loadFlows: async () => {
    const readGeneration = flowReadGeneration;
    set({ isLoading: true, apiError: null });
    try {
      const data = await fetchFlows();
      if (readGeneration !== flowReadGeneration) {
        set({ isLoading: false });
        return;
      }
      set({ flows: transformFlows(data.flows), isLoading: false });
    } catch (e) {
      if (readGeneration !== flowReadGeneration) {
        set({ isLoading: false });
        return;
      }
      const msg = e instanceof Error ? e.message : 'Failed to load flows';
      set({ apiError: msg, isLoading: false });
      get().addToast(msg, 'error');
    }
  },

  addFlow: async (flow) => {
    flowReadGeneration += 1;
    try {
      await apiCreateFlow({
        flow_id: flow.id,
        yaml_content: flow.content,
        filename: flow.name,
      });
      const data = await fetchFlows({fresh: true});
      const confirmedFlows = transformFlows(data.flows);
      if (!confirmedFlows.some((candidate) => candidate.id === flow.id)) {
        throw new Error('Flow creation was not confirmed');
      }
      set({ flows: confirmedFlows });
      return { ok: true };
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to create flow';
      get().addToast(msg, 'error');
      return { ok: false, error: msg };
    } finally {
      flowReadGeneration += 1;
    }
  },

  updateFlow: async (id, content) => {
    flowReadGeneration += 1;
    try {
      await apiUpdateFlow(id, { yaml_content: content });
      const [data, detail] = await Promise.all([
        fetchFlows({fresh: true}),
        fetchFlowDetail(id, {fresh: true}),
      ]);
      const confirmedFlows = transformFlows(data.flows);
      if (
        !confirmedFlows.some((candidate) => candidate.id === id)
        || detail.flow_id !== id
        || detail.yaml_content !== content
      ) {
        throw new Error('Flow update was not confirmed');
      }
      set({ flows: confirmedFlows });
      return { ok: true };
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to update flow';
      get().addToast(msg, 'error');
      return { ok: false, error: msg };
    } finally {
      flowReadGeneration += 1;
    }
  },

  deleteFlow: async (id) => {
    flowReadGeneration += 1;
    try {
      await apiDeleteFlow(id);
      const data = await fetchFlows({fresh: true});
      const confirmedFlows = transformFlows(data.flows);
      if (confirmedFlows.some((candidate) => candidate.id === id)) {
        throw new Error('Flow deletion was not confirmed');
      }
      set({ flows: confirmedFlows });
      return { ok: true };
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to delete flow';
      get().addToast(msg, 'error');
      return { ok: false, error: msg };
    } finally {
      flowReadGeneration += 1;
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
    const readGeneration = profileReadGeneration;
    try {
      const data = await fetchProfile();
      if (readGeneration !== profileReadGeneration) return;
      set({ profile: transformProfile(data.profile) });
    } catch (e) {
      if (readGeneration !== profileReadGeneration) return;
      // Profile not found (404) is expected for new users
      const msg = e instanceof Error ? e.message : '';
      if (!msg.includes('Profile not found')) {
        set({ apiError: msg });
      }
    }
  },

  updateProfile: async (profileUpdate) => {
    profileReadGeneration += 1;
    try {
      const current = get().profile;
      const submittedUsername = profileUpdate.username ?? current.username;
      const submittedLanguage = profileUpdate.language ?? current.language;
      if (submittedUsername.trim() === '') {
        throw new Error('username is required and must be a non-empty string');
      }
      if (submittedUsername.length > 100) {
        throw new Error('username must be 100 characters or less');
      }
      if (!allowedProfileLanguages.has(submittedLanguage)) {
        throw new Error('language is not allowed');
      }
      const expected: Profile = {
        avatar: profileUpdate.avatar ?? current.avatar,
        username: submittedUsername.trim(),
        language: submittedLanguage,
        job: profileUpdate.job ?? current.job,
        connected: current.connected,
      };
      const payload: Record<string, unknown> = {
        username: expected.username,
        language: expected.language,
        icon: expected.avatar,
        occupation: expected.job,
      };
      await apiUpdateProfile(payload);
      const data = await fetchProfile({fresh: true});
      const confirmed = transformProfile(data.profile);
      if (
        confirmed.avatar !== expected.avatar
        || confirmed.username !== expected.username
        || confirmed.language !== expected.language
        || confirmed.job !== expected.job
      ) {
        throw new Error('Profile update was not confirmed');
      }
      set({ profile: confirmed });
      return { ok: true };
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to update profile';
      get().addToast(msg, 'error');
      return { ok: false, error: msg };
    } finally {
      profileReadGeneration += 1;
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
