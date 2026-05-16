export type Theme = 'Rumi' | 'Minimal' | 'Standard' | 'Rounded';

export type ColorMode = 'light' | 'dark';

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

export interface RuntimeHealthPatch {
  status?: 'ok' | 'error';
  panel_ready?: boolean;
  runtime_ready?: boolean;
  runtime_status?: RuntimeStatus;
  runtime_error?: string | null;
}

export interface AppState {
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
  setRuntimeHealth: (health: RuntimeHealthPatch) => void;
  refreshRuntimeHealth: () => Promise<void>;

  packs: Pack[];
  loadPacks: () => Promise<void>;
  togglePack: (id: string) => Promise<void>;

  flows: Flow[];
  loadFlows: () => Promise<void>;
  addFlow: (flow: Flow) => Promise<void>;
  updateFlow: (id: string, content: string) => Promise<void>;
  deleteFlow: (id: string) => Promise<void>;

  dashboard: DashboardData;
  loadDashboard: () => Promise<void>;
  setKernelStatus: (status: DashboardData['kernelStatus']) => void;
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
