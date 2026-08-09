import {create} from 'zustand';
import {
  approvePack as apiApprovePack,
  checkHealth,
  disablePack as apiDisablePack,
  enablePack as apiEnablePack,
  fetchFrontendCatalog,
  fetchPacks,
  installPack as apiInstallPack,
  invokeFrontendCapability,
  revokePackApproval as apiRevokePackApproval,
} from './lib/api';
import type {ApiDynamicFrontendCatalog, ApiSupervisorDashboard} from './lib/apiTypes';
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

export interface PackOperation {
  operationId: string;
  contractId: string;
  providerId: string;
  capabilities: string[];
  inputSchema: Record<string, unknown>;
  invokable: boolean;
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
  operations?: PackOperation[];
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
  packApprovalPending: Record<string, boolean>;
  frontendCatalog: ApiDynamicFrontendCatalog | null;
  frontendCatalogLoading: boolean;
  frontendCatalogError: string | null;
  packOperationPending: Record<string, boolean>;
  loadPacks: () => Promise<void>;
  loadFrontendCatalog: () => Promise<void>;
  invokePackOperation: (
    packId: string,
    operationId: string,
    payload: Record<string, unknown>,
  ) => Promise<unknown>;
  installPack: (id: string) => Promise<void>;
  approvePack: (id: string) => Promise<void>;
  revokePackApproval: (id: string) => Promise<void>;
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
let frontendCatalogLoadPromise: Promise<void> | null = null;
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
  packApprovalPending: {},
  frontendCatalog: null,
  frontendCatalogLoading: false,
  frontendCatalogError: null,
  packOperationPending: {},

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
          if (
            before === after
            && !latestState.packTogglePending[pack.id]
            && !latestState.packApprovalPending[pack.id]
          ) return pack;
          const current = currentById.get(pack.id);
          if (!current) return pack;
          if (
            latestState.packApprovalPending[pack.id]
            || (current.approvalStatus === 'revoked' && !current.approved)
          ) {
            return {
              ...pack,
              enabled: current.enabled,
              approved: current.approved,
              approvalStatus: current.approvalStatus,
              approvalReason: current.approvalReason,
              approvalIssues: current.approvalIssues,
            };
          }
          return {...pack, enabled: current.enabled};
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

  loadFrontendCatalog: () => {
    if (frontendCatalogLoadPromise) return frontendCatalogLoadPromise;
    set({
      frontendCatalogLoading: true,
      frontendCatalogError: null,
      frontendCatalog: null,
    });
    frontendCatalogLoadPromise = (async () => {
      try {
        const catalog = await fetchFrontendCatalog();
        if (
          !catalog.profile_id
          || !catalog.plan_hash
          || !catalog.catalog_hash
          || !Array.isArray(catalog.contributions)
        ) {
          throw new Error('Tobkiri returned an invalid dynamic frontend catalog.');
        }
        set({frontendCatalog: catalog, frontendCatalogError: null});
      } catch (error) {
        const message = error instanceof Error
          ? error.message
          : 'Tobkiri dynamic frontend catalog is unavailable.';
        set({frontendCatalog: null, frontendCatalogError: message});
      }
    })().finally(() => {
      frontendCatalogLoadPromise = null;
      set({frontendCatalogLoading: false});
    });
    return frontendCatalogLoadPromise;
  },

  invokePackOperation: async (packId, operationId, payload) => {
    const operationKey = `${packId}:${operationId}`;
    const state = get();
    const pack = state.packs.find((candidate) => candidate.id === packId);
    if (!pack || !pack.installed || !pack.enabled || !pack.approved) {
      throw new Error(
        'Tobkiri requires an installed, approved, enabled Pack before invoking its operation.',
      );
    }
    if (state.packOperationPending[operationKey]) {
      throw new Error('Tobkiri operation is already in progress.');
    }
    const operation = (pack.operations ?? []).find(
      (candidate) => candidate.operationId === operationId,
    );
    const catalog = state.frontendCatalog;
    const contribution = catalog?.contributions.find((candidate) => (
      candidate.owner_pack_id === packId
      && candidate.action_contract
      && (
        candidate.operation_id === operationId
        || candidate.contribution_id === operationId
        || candidate.label === operationId
      )
    ));
    if (!operation || !catalog || catalog.quarantined_pack_ids.includes(packId) || !contribution) {
      throw new Error(
        'Tobkiri has not exposed this Pack operation in the current v4 capability catalog.',
      );
    }
    if (
      !operation.invokable
      || contribution.action_contract !== operation.contractId
    ) {
      throw new Error('Tobkiri has not verified this Pack operation for invocation.');
    }

    set((current) => ({
      packOperationPending: {...current.packOperationPending, [operationKey]: true},
    }));
    try {
      const result = await invokeFrontendCapability({
        profileId: catalog.profile_id,
        planHash: catalog.plan_hash,
        catalogHash: catalog.catalog_hash,
        contributionId: contribution.contribution_id,
        ownerPackId: contribution.owner_pack_id,
        contractId: contribution.action_contract,
        payload,
      });
      await Promise.all([get().loadPacks(), get().loadFrontendCatalog()]);
      return result;
    } finally {
      set((current) => {
        const pending = {...current.packOperationPending};
        delete pending[operationKey];
        return {packOperationPending: pending};
      });
    }
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

  revokePackApproval: async (id) => {
    const state = get();
    const pack = state.packs.find((candidate) => candidate.id === id);
    if (
      !pack
      || !pack.installed
      || !pack.approved
      || pack.type === 'core'
      || state.packApprovalPending[id]
    ) return;

    const version = (packMutationVersions.get(id) ?? 0) + 1;
    packMutationVersions.set(id, version);
    set((current) => ({
      packApprovalPending: {...current.packApprovalPending, [id]: true},
    }));
    try {
      const response = await apiRevokePackApproval(id);
      if (
        response.pack_id !== id
        || response.approved
        || response.approval_status !== 'revoked'
        || response.enabled !== false
      ) {
        throw new Error('Tobkiri did not confirm Pack approval revocation.');
      }
      if (packMutationVersions.get(id) === version) {
        set((current) => ({
          packs: current.packs.map((candidate) => (
            candidate.id === id
              ? {
                ...candidate,
                enabled: false,
                approved: false,
                approvalStatus: 'revoked',
                approvalReason: 'approval_revoked',
                approvalIssues: ['approval_revoked'],
                profileId: response.profile_id,
                workspaceId: response.workspace_id,
                profileRevision: response.profile_revision,
                planDigest: response.plan_digest,
                catalogRevision: response.catalog_revision,
              }
              : candidate
          )),
        }));
      }
      await Promise.all([get().loadPacks(), get().loadFrontendCatalog()]);
      get().addToast('Pack approval revoked.', 'success');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to revoke Pack approval';
      get().addToast(message, 'error');
      throw error;
    } finally {
      set((current) => {
        const pending = {...current.packApprovalPending};
        delete pending[id];
        return {packApprovalPending: pending};
      });
    }
  },

  togglePack: async (id) => {
    const state = get();
    const pack = state.packs.find((candidate) => candidate.id === id);
    if (!pack || state.packTogglePending[id]) return false;

    const version = (packMutationVersions.get(id) ?? 0) + 1;
    packMutationVersions.set(id, version);
    set((current) => ({
      packTogglePending: {...current.packTogglePending, [id]: true},
    }));

    try {
      const expectedEnabled = !pack.enabled;
      const response = pack.enabled
        ? await apiDisablePack(id)
        : await apiEnablePack(id);
      if (response.pack_id !== id || response.enabled !== expectedEnabled) {
        throw new Error('Tobkiri did not confirm the requested Pack state.');
      }
      if (packMutationVersions.get(id) === version) {
        set((current) => ({
          packs: current.packs.map((candidate) => (
            candidate.id === id
              ? {
                ...candidate,
                enabled: response.enabled,
                profileId: response.profile_id,
                workspaceId: response.workspace_id,
                profileRevision: response.profile_revision,
                planDigest: response.plan_digest,
                catalogRevision: response.catalog_revision,
              }
              : candidate
          )),
        }));
      }
      await Promise.all([get().loadPacks(), get().loadFrontendCatalog()]);
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
