import type {
  ApiDashboard,
  ApiDynamicFrontendCatalog,
  ApiPresentationSelection,
  ApiResponse,
  ApiPresentationState,
  BackgroundControlStatus,
  DebugApprovalDuration,
  DebugApprovalStatus,
  DesktopSystemInfo,
  HealthResponseData,
  KernelRestartResponseData,
  FrontendCapabilityInvocation,
  PackApprovalResponseData,
  PackInstallResponseData,
  PackToggleResponseData,
  PacksResponseData,
  PresentationLaunchResponse,
} from './apiTypes';
import {
  GetRequestCoordinator,
  RequestInvalidatedError,
  type GetRequestSnapshot,
} from './getRequestCoordinator';

const API_BASE_URL =
  (import.meta as ImportMeta & {env?: Record<string, string>}).env?.VITE_API_BASE_URL ?? '';
const PANEL_CSRF_STORAGE_KEY = 'rumi-panel-csrf';
const PANEL_AUTH_EXCHANGE_PATH = '/api/panel/auth/exchange';
let panelBootstrapPromise: Promise<void> | null = null;
let panelBootstrapCodeInFlight: string | null = null;
let panelSessionRecoveryPromise: Promise<boolean> | null = null;
const getRequestCoordinator = new GetRequestCoordinator();
const FOREGROUND_GET_TIMEOUT_MS = 10_000;

type TauriInvoke = <T>(command: string, args?: Record<string, unknown>) => Promise<T>;
type TauriWindow = Window & {
  __TAURI_INTERNALS__?: unknown;
  __TAURI__?: {
    core?: {
      invoke?: TauriInvoke;
    };
  };
};

function getStoredPanelCsrfToken(): string {
  return sessionStorage.getItem(PANEL_CSRF_STORAGE_KEY) || '';
}

function setStoredPanelCsrfToken(token: string): void {
  if (!token) {
    sessionStorage.removeItem(PANEL_CSRF_STORAGE_KEY);
    return;
  }
  sessionStorage.setItem(PANEL_CSRF_STORAGE_KEY, token);
}

function isUnsafeMethod(method: string): boolean {
  return method === 'POST' || method === 'PUT' || method === 'DELETE' || method === 'PATCH';
}

function isSetupApiPath(path: string): boolean {
  return path === '/api/setup' || path.startsWith('/api/setup/');
}

function isFrontendContractPath(path: string): boolean {
  return path.startsWith('/api/contracts/defaultspack/');
}

function isPanelSessionApiPath(path: string): boolean {
  return isSetupApiPath(path) || isFrontendContractPath(path);
}

function frontendContractPath(method: string, target: string): string {
  const operation = `${method.toUpperCase()} ${target}`;
  return `/api/contracts/defaultspack/${encodeURIComponent(operation)}`;
}

export function hasPendingPanelBootstrapCode(href = window.location.href): boolean {
  return new URL(href).searchParams.has('code');
}

async function exchangePanelBootstrapCode(
  code: string,
  currentRequestSignal?: AbortSignal,
): Promise<void> {
  const url = new URL(window.location.href);
  if (!code) return;

  const response = await fetch(`${API_BASE_URL}${PANEL_AUTH_EXCHANGE_PATH}`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({code}),
  });

  if (!response.ok) {
    let errorMessage = `Panel bootstrap failed: ${response.status} ${response.statusText}`;
    try {
      const errorBody: ApiResponse<unknown> = await response.json();
      if (errorBody.error) errorMessage = errorBody.error;
    } catch {
      // Use the HTTP status when the server did not return an error envelope.
    }
    throw new Error(errorMessage);
  }

  const envelope: ApiResponse<{csrf_token: string}> = await response.json();
  if (!envelope.success || !envelope.data?.csrf_token) {
    throw new Error(envelope.error || 'Panel bootstrap failed');
  }

  setStoredPanelCsrfToken(envelope.data.csrf_token);
  getRequestCoordinator.invalidate({preserveSignal: currentRequestSignal});
  url.searchParams.delete('code');
  window.history.replaceState({}, document.title, url.pathname + url.search + url.hash);
}

function getTauriInvoke(): TauriInvoke | null {
  const maybeWindow = window as TauriWindow;
  const invoke = maybeWindow.__TAURI__?.core?.invoke;
  return typeof invoke === 'function' ? invoke : null;
}

function isLikelyTauriShell(): boolean {
  const maybeWindow = window as TauriWindow;
  return Boolean(maybeWindow.__TAURI__ || maybeWindow.__TAURI_INTERNALS__);
}

async function loadTauriInvoke(): Promise<TauriInvoke | null> {
  const globalInvoke = getTauriInvoke();
  if (globalInvoke) return globalInvoke;
  if (!isLikelyTauriShell()) return null;
  try {
    const mod = await import('@tauri-apps/api/core');
    return mod.invoke as TauriInvoke;
  } catch {
    return null;
  }
}

async function requireTauriInvoke(operation: string): Promise<TauriInvoke> {
  const invoke = await loadTauriInvoke();
  if (!invoke) {
    throw new Error(`${operation} is only available in Tobkiri Launcher.`);
  }
  return invoke;
}

export function isDesktopShellAvailable(): boolean {
  return getTauriInvoke() !== null || isLikelyTauriShell();
}

export async function openExternalUrl(url: string): Promise<void> {
  const invoke = await loadTauriInvoke();
  if (invoke) {
    await invoke('open_external_url', {url});
    return;
  }
  window.location.href = url;
}

export async function sendToBackground(): Promise<void> {
  const invoke = await requireTauriInvoke('Background control');
  await invoke<void>('send_to_background');
}

export async function showAppWindow(): Promise<void> {
  const invoke = await requireTauriInvoke('Window restore');
  await invoke<void>('show_app_window');
}

export async function fetchBackgroundControlStatus(): Promise<BackgroundControlStatus | null> {
  const invoke = await loadTauriInvoke();
  return invoke ? invoke<BackgroundControlStatus>('get_background_control_status') : null;
}

export async function fetchDesktopSystemInfo(): Promise<DesktopSystemInfo | null> {
  const invoke = await loadTauriInvoke();
  return invoke ? invoke<DesktopSystemInfo>('get_desktop_system_info') : null;
}

export async function fetchDebugApprovalStatus(): Promise<DebugApprovalStatus | null> {
  const invoke = await loadTauriInvoke();
  return invoke ? invoke<DebugApprovalStatus>('debug_approval_status') : null;
}

export async function armDebugApproval(duration: DebugApprovalDuration): Promise<DebugApprovalStatus> {
  const invoke = await requireTauriInvoke('Developer Debug Approval');
  return invoke<DebugApprovalStatus>('arm_debug_approval', {duration});
}

export async function revokeDebugApproval(): Promise<DebugApprovalStatus> {
  const invoke = await requireTauriInvoke('Developer Debug Approval');
  return invoke<DebugApprovalStatus>('revoke_debug_approval');
}

export async function launchDefaultspackDesktop(): Promise<string> {
  const invoke = await requireTauriInvoke('Defaultspack desktop launch');
  return invoke<string>('launch_defaultspack_desktop');
}

export async function fetchPresentationState(): Promise<ApiPresentationState> {
  const invoke = await requireTauriInvoke('Presentation selection');
  return invoke<ApiPresentationState>('get_presentation_catalog');
}

export async function selectPresentation(
  selection: ApiPresentationSelection,
): Promise<ApiPresentationState> {
  const invoke = await requireTauriInvoke('Presentation selection');
  return invoke<ApiPresentationState>('select_presentation', {selection});
}

export async function launchSelectedPresentation(): Promise<PresentationLaunchResponse> {
  const invoke = await requireTauriInvoke('Presentation launch');
  return invoke<PresentationLaunchResponse>('launch_selected_presentation');
}

async function requestDesktopPanelBootstrapCode(): Promise<string | null> {
  const invoke = await loadTauriInvoke();
  return invoke ? invoke<string>('reauthorize_panel_session') : null;
}

function isRecoverablePanelAuthError(status: number, errorMessage: string): boolean {
  return status === 401 || /Unauthorized|Invalid or expired code/i.test(errorMessage);
}

async function recoverExpiredPanelSession(currentRequestSignal?: AbortSignal): Promise<boolean> {
  if (panelSessionRecoveryPromise) return panelSessionRecoveryPromise;

  panelSessionRecoveryPromise = (async () => {
    if (hasPendingPanelBootstrapCode()) {
      await bootstrapPanelSession(currentRequestSignal);
      return true;
    }

    const code = await requestDesktopPanelBootstrapCode();
    if (!code) return false;
    await exchangePanelBootstrapCode(code, currentRequestSignal);
    return true;
  })();

  try {
    return await panelSessionRecoveryPromise;
  } finally {
    panelSessionRecoveryPromise = null;
  }
}

export async function bootstrapPanelSession(currentRequestSignal?: AbortSignal): Promise<void> {
  const url = new URL(window.location.href);
  const code = url.searchParams.get('code');
  if (!code) return;

  if (panelBootstrapPromise && panelBootstrapCodeInFlight === code) {
    return panelBootstrapPromise;
  }

  panelBootstrapCodeInFlight = code;
  panelBootstrapPromise = exchangePanelBootstrapCode(code, currentRequestSignal);
  try {
    await panelBootstrapPromise;
  } finally {
    panelBootstrapPromise = null;
    panelBootstrapCodeInFlight = null;
  }
}

async function ensurePanelSessionForRequest(
  path: string,
  method: string,
  currentRequestSignal?: AbortSignal,
): Promise<void> {
  if (!isPanelSessionApiPath(path)) return;
  if (!isUnsafeMethod(method) && !hasPendingPanelBootstrapCode() && !panelBootstrapPromise) return;
  if (panelBootstrapPromise || hasPendingPanelBootstrapCode()) {
    await bootstrapPanelSession(currentRequestSignal);
  }
}

export interface ApiRequestPolicy {
  mode?: 'foreground' | 'prefetch';
  timeoutMs?: number;
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  requestPolicy: ApiRequestPolicy = {},
): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const method = (options.method || 'GET').toUpperCase();

  const fetchRequest = async (
    allowPanelRecovery = true,
    signal?: AbortSignal,
  ): Promise<T> => {
    await ensurePanelSessionForRequest(path, method, signal);

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string> | undefined),
    };
    if (isFrontendContractPath(path)) {
      headers['X-Tobkiri-Request-ID'] = crypto.randomUUID();
    }
    if (isUnsafeMethod(method)) {
      const csrfToken = getStoredPanelCsrfToken();
      if (csrfToken) headers['X-Rumi-CSRF'] = csrfToken;
    }

    const response = await fetch(url, {
      ...options,
      method,
      credentials: 'same-origin',
      headers,
      signal: signal ?? options.signal,
    });

    if (!response.ok) {
      let errorMessage = response.status === 429
        ? 'Too many requests reached the local panel. Please wait a moment and try again.'
        : `API Error: ${response.status} ${response.statusText}`;
      try {
        const errorBody: ApiResponse<unknown> = await response.json();
        if (errorBody.error) errorMessage = errorBody.error;
      } catch {
        // Use the default HTTP error.
      }
      if (
        allowPanelRecovery &&
        isPanelSessionApiPath(path) &&
        isRecoverablePanelAuthError(response.status, errorMessage) &&
        await recoverExpiredPanelSession(signal)
      ) {
        return fetchRequest(false, signal);
      }
      throw new Error(errorMessage);
    }

    const envelope: ApiResponse<T> = await response.json();
    if (!envelope.success) {
      const errorMessage = envelope.error || 'Unknown API error';
      if (
        allowPanelRecovery &&
        isPanelSessionApiPath(path) &&
        isRecoverablePanelAuthError(response.status, errorMessage) &&
        await recoverExpiredPanelSession(signal)
      ) {
        return fetchRequest(false, signal);
      }
      throw new Error(errorMessage);
    }
    return envelope.data as T;
  };

  if (method === 'GET') {
    const mode = requestPolicy.mode ?? 'foreground';
    const timeoutMs = requestPolicy.timeoutMs ?? FOREGROUND_GET_TIMEOUT_MS;
    const executeGet = (allowInvalidationRetry: boolean): Promise<T> => (
      getRequestCoordinator.request({
        key: `${method}:${url}`,
        mode,
        timeoutMs,
        factory: (signal) => fetchRequest(true, signal),
      }).catch((error) => {
        if (
          allowInvalidationRetry &&
          mode === 'foreground' &&
          error instanceof RequestInvalidatedError
        ) {
          return executeGet(false);
        }
        throw error;
      })
    );
    return executeGet(true);
  }

  try {
    return await fetchRequest();
  } finally {
    getRequestCoordinator.invalidate();
  }
}

export function prefetchApiGet<T>(
  path: string,
  options: {timeoutMs?: number} = {},
): Promise<T> {
  return apiFetch<T>(path, {}, {
    mode: 'prefetch',
    timeoutMs: options.timeoutMs ?? 2_500,
  });
}

export function clearApiPrefetchCache(): void {
  getRequestCoordinator.invalidate();
}

export function invalidateApiGetCache(): void {
  getRequestCoordinator.invalidate();
}

export function getApiRequestCacheSnapshot(): GetRequestSnapshot {
  return getRequestCoordinator.snapshot();
}

export function fetchDashboard(): Promise<ApiDashboard> {
  return apiFetch<ApiDashboard>(frontendContractPath('GET', '/api/home/dashboard'));
}

export async function fetchFrontendCatalog(): Promise<ApiDynamicFrontendCatalog> {
  const data = await apiFetch<{dynamic_host?: ApiDynamicFrontendCatalog | null}>(
    frontendContractPath('GET', '/api/ui/catalog'),
  );
  if (!data.dynamic_host) {
    throw new Error('Tobkiri dynamic frontend catalog is unavailable.');
  }
  return data.dynamic_host;
}

export function invokeFrontendCapability(
  request: FrontendCapabilityInvocation,
): Promise<unknown> {
  return apiFetch<unknown>(frontendContractPath('POST', '/api/ui/capability/invoke'), {
    method: 'POST',
    body: JSON.stringify({
      request_id: crypto.randomUUID(),
      expires_at: Date.now() / 1000 + 30,
      profile_id: request.profileId,
      plan_hash: request.planHash,
      catalog_hash: request.catalogHash,
      contribution_id: request.contributionId,
      owner_pack_id: request.ownerPackId,
      contract_id: request.contractId,
      payload: request.payload,
    }),
  });
}

function dispatchPackControl<T>(
  operationId: string,
  payload: Record<string, unknown> = {},
): Promise<T> {
  const targets: Record<string, string> = {
    'approval.approve': '/api/pack-control/approval-approve',
    'approval.candidate': '/api/pack-control/approval-candidate',
    'approval.revoke': '/api/pack-control/approval-revoke',
    'pack.disable': '/api/pack-control/disable',
    'pack.enable': '/api/pack-control/enable',
    'pack.install': '/api/pack-control/install',
    'runtime.restart': '/api/pack-control/restart',
  };
  if (operationId === 'catalog.read') {
    return apiFetch<T>(frontendContractPath('GET', '/api/pack-control/catalog'));
  }
  const target = targets[operationId];
  if (!target) throw new Error(`Unselected Pack control operation: ${operationId}`);
  return apiFetch<T>(frontendContractPath('POST', target), {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function fetchPacks(): Promise<PacksResponseData> {
  return dispatchPackControl<PacksResponseData>('catalog.read');
}

export async function installPack(id: string): Promise<PackInstallResponseData> {
  return dispatchPackControl('pack.install', {pack_id: id});
}

export async function approvePack(id: string): Promise<PackApprovalResponseData> {
  const candidate = await dispatchPackControl<{candidate_id: string}>('approval.candidate', {pack_id: id});
  return dispatchPackControl<PackApprovalResponseData>('approval.approve', {
    pack_id: id,
    candidate_id: candidate.candidate_id,
  });
}

export function enablePack(id: string): Promise<PackToggleResponseData> {
  return dispatchPackControl<PackToggleResponseData>('pack.enable', {pack_id: id});
}

export function disablePack(id: string): Promise<PackToggleResponseData> {
  return dispatchPackControl<PackToggleResponseData>('pack.disable', {pack_id: id});
}

export function revokePackApproval(id: string): Promise<PackApprovalResponseData> {
  return dispatchPackControl<PackApprovalResponseData>('approval.revoke', {pack_id: id});
}

export function restartKernel(): Promise<KernelRestartResponseData> {
  return dispatchPackControl<KernelRestartResponseData>('runtime.restart');
}

export function checkHealth(): Promise<HealthResponseData> {
  return apiFetch<HealthResponseData>('/health');
}
