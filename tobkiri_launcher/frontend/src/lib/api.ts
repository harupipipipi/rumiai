import type {
  ApiDashboard,
  ApiDynamicFrontendCatalog,
  ApiPackVMConsent,
  ApiPackVMCleanupResult,
  ApiPackVMDoctor,
  ApiPackVMOperation,
  ApiPackVMProvisioningPlan,
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
import {
  normalizePackVMConsent,
  normalizePackVMCleanup,
  normalizePackVMDoctor,
  normalizePackVMOperation,
  normalizePackVMPlan,
} from './packvmLifecycle';
import {
  generatedRouteFor,
  VERIFIED_GENERATED_FRONTEND_CONTRACT_MAP,
} from './generatedFrontendContractMap';

const API_BASE_URL =
  (import.meta as ImportMeta & {env?: Record<string, string>}).env?.VITE_API_BASE_URL ?? '';
const PANEL_CSRF_STORAGE_KEY = 'rumi-panel-csrf';
const PANEL_AUTH_EXCHANGE_PATH = '/api/panel/auth/exchange';
export type FrontendContractMethod = 'GET' | 'POST';

const EXACT_NON_MAP_API_ROUTES = [
  {method: 'POST', path: PANEL_AUTH_EXCHANGE_PATH},
  {method: 'GET', path: '/api/setup/packs'},
  {method: 'POST', path: '/api/setup/packs/install'},
  {method: 'POST', path: '/api/v4/packvm/prepare'},
  {method: 'POST', path: '/api/v4/packvm/consent'},
  {method: 'POST', path: '/api/v4/packvm/provision'},
  {method: 'POST', path: '/api/v4/packvm/cancel'},
  {method: 'GET', path: '/api/v4/packvm/doctor'},
  {method: 'POST', path: '/api/v4/packvm/stop'},
  {method: 'POST', path: '/api/v4/packvm/cleanup'},
  {method: 'GET', path: '/health'},
] as const satisfies ReadonlyArray<{
  method: FrontendContractMethod;
  path: string;
}>;
const EXACT_PACKVM_LIFECYCLE_PATHS = new Set([
  '/api/v4/packvm/prepare',
  '/api/v4/packvm/consent',
  '/api/v4/packvm/provision',
  '/api/v4/packvm/cancel',
  '/api/v4/packvm/doctor',
  '/api/v4/packvm/stop',
  '/api/v4/packvm/cleanup',
]);
let panelBootstrapPromise: Promise<void> | null = null;
let panelBootstrapCodeInFlight: string | null = null;
let panelSessionRecoveryPromise: Promise<boolean> | null = null;
const getRequestCoordinator = new GetRequestCoordinator();
const FOREGROUND_GET_TIMEOUT_MS = 10_000;
const MUTATION_TIMEOUT_MS = 10_000;

export class ApiRequestTimeoutError extends Error {
  constructor(method: string, path: string, timeoutMs: number) {
    super(`${method} request timed out after ${timeoutMs}ms: ${path}`);
    this.name = 'ApiRequestTimeoutError';
  }
}

export class ApiContractError extends Error {
  readonly data: unknown;

  constructor(message: string, data: unknown) {
    super(message);
    this.name = 'ApiContractError';
    this.data = data;
  }
}

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
  return path === '/api/setup/packs' || path === '/api/setup/packs/install';
}

interface ParsedFrontendContractPath {
  method: FrontendContractMethod;
  route: ReturnType<typeof generatedRouteFor>;
}

function parseFrontendContractPath(path: string): ParsedFrontendContractPath | null {
  const match = /^\/api\/contracts\/defaultspack\/([^/?#]+)(?:\?([^#]*))?$/.exec(path);
  if (!match) return null;
  let operation: string;
  try {
    operation = decodeURIComponent(match[1]);
  } catch {
    return null;
  }
  const separator = operation.indexOf(' ');
  if (separator <= 0) return null;
  const method = operation.slice(0, separator);
  const target = operation.slice(separator + 1);
  if (method !== 'GET' && method !== 'POST') return null;
  let route;
  try {
    route = generatedRouteFor(
      VERIFIED_GENERATED_FRONTEND_CONTRACT_MAP,
      method,
      target,
    );
  } catch {
    return null;
  }
  const query = match[2];
  if (query !== undefined) {
    if (!query || method !== 'GET' || route.targets.length !== 1) return null;
    const allowedKeys = new Set(route.targets[0].allowed_payload_keys);
    const params = new URLSearchParams(query);
    const seen = new Set<string>();
    for (const [key, value] of params.entries()) {
      if (!allowedKeys.has(key) || seen.has(key) || !value) return null;
      seen.add(key);
    }
    if (seen.size === 0) return null;
  }
  return {method, route};
}

function isFrontendContractPath(path: string): boolean {
  return parseFrontendContractPath(path) !== null;
}

function exactNonMapMethodForPath(path: string): FrontendContractMethod | null {
  const route = EXACT_NON_MAP_API_ROUTES.find((candidate) => candidate.path === path);
  return route?.method ?? null;
}

function isPackVMProgressPath(path: string): boolean {
  const separator = path.indexOf('?');
  if (separator <= 0 || path.slice(0, separator) !== '/api/v4/packvm/progress') {
    return false;
  }
  const query = path.slice(separator + 1);
  const match = /^operation_id=([^&#=]+)$/.exec(query);
  if (!match) return false;
  let operationId: string;
  try {
    operationId = decodeURIComponent(match[1]);
  } catch {
    return false;
  }
  return operationId.length > 0 && encodeURIComponent(operationId) === match[1];
}

function isPackVMLifecyclePath(path: string): boolean {
  return EXACT_PACKVM_LIFECYCLE_PATHS.has(path) || isPackVMProgressPath(path);
}

function isPanelSessionApiPath(path: string): boolean {
  return isSetupApiPath(path) || isFrontendContractPath(path) || isPackVMLifecyclePath(path);
}

function isExactAllowedApiRequest(path: string, method: string): boolean {
  const contract = parseFrontendContractPath(path);
  if (contract) return method === contract.method;
  const nonMapMethod = exactNonMapMethodForPath(path);
  if (nonMapMethod) return method === nonMapMethod;
  if (isPackVMProgressPath(path)) return method === 'GET';
  return false;
}

function frontendContractPath(method: FrontendContractMethod, target: string): string {
  if (method !== 'GET' && method !== 'POST') {
    throw new Error('The generated v4 contract method is unsupported.');
  }
  try {
    generatedRouteFor(
      VERIFIED_GENERATED_FRONTEND_CONTRACT_MAP,
      method,
      target,
    );
  } catch {
    throw new Error(`The logical target is not declared by the verified frontend Contract Map: ${method} ${target}`);
  }
  const operation = `${method.toUpperCase()} ${target}`;
  return `/api/contracts/defaultspack/${encodeURIComponent(operation)}`;
}

function assertLogicalContractTarget(method: FrontendContractMethod, target: string): void {
  if (
    !target.startsWith('/api/')
    || target.startsWith('/api/contracts/')
    || target.includes('..')
    || target.includes('//')
    || target.includes('\\')
    || target.includes('?')
    || target.includes('#')
  ) {
    throw new Error('The generated v4 contract target is invalid.');
  }
  if (method !== 'GET' && method !== 'POST') {
    throw new Error('The generated v4 contract method is unsupported.');
  }
}

/**
 * Call one target supplied by the digest-pinned v4 frontend contract map.
 *
 * The target is intentionally injected by the generated map; this helper
 * does not discover routes, synthesize function paths, or provide a legacy
 * HTTP fallback.
 */
export function fetchFrontendContractOperation<T>(
  method: FrontendContractMethod,
  target: string,
  payload?: Record<string, unknown>,
): Promise<T> {
  assertLogicalContractTarget(method, target);
  const route = generatedRouteFor(
    VERIFIED_GENERATED_FRONTEND_CONTRACT_MAP,
    method,
    target,
  );
  if (route.targets.length !== 1) {
    throw new Error('The generated v4 target has multiple operations; select an exact operation binding first.');
  }
  const allowedKeys = new Set(route.targets[0].allowed_payload_keys);
  if (payload && Object.keys(payload).some((key) => !allowedKeys.has(key))) {
    throw new Error('The generated v4 contract payload contains an unknown key.');
  }
  const query = method === 'GET' && payload && Object.keys(payload).length > 0
    ? `?${new URLSearchParams(
      Object.entries(payload).map(([key, value]) => [key, String(value)]),
    ).toString()}`
    : '';
  const path = frontendContractPath(method, target);
  return apiFetch<T>(query ? `${path}${query}` : path, method === 'POST'
    ? {method, body: JSON.stringify(payload ?? {})}
    : {});
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
  if (!isExactAllowedApiRequest(path, method)) {
    throw new Error(`The frontend request is not in the exact method/path allowlist: ${method} ${path}`);
  }

  const fetchRequest = async (
    allowPanelRecovery = true,
    signal?: AbortSignal,
  ): Promise<T> => {
    await ensurePanelSessionForRequest(path, method, signal);

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string> | undefined),
    };
    if (isFrontendContractPath(path) || (isPackVMLifecyclePath(path) && isUnsafeMethod(method))) {
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
      let errorData: unknown = null;
      try {
        const errorBody: ApiResponse<unknown> = await response.json();
        if (errorBody.error) errorMessage = errorBody.error;
        errorData = errorBody.data;
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
      throw new ApiContractError(errorMessage, errorData);
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
      throw new ApiContractError(errorMessage, envelope.data);
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
    const timeoutMs = requestPolicy.timeoutMs ?? MUTATION_TIMEOUT_MS;
    const controller = new AbortController();
    let timeout: ReturnType<typeof globalThis.setTimeout> | undefined;
    const externalSignal = options.signal;
    const abortFromExternalSignal = () => {
      controller.abort(externalSignal?.reason);
    };

    if (externalSignal) {
      if (externalSignal.aborted) {
        abortFromExternalSignal();
      } else {
        externalSignal.addEventListener('abort', abortFromExternalSignal, {once: true});
      }
    }

    const request = fetchRequest(true, controller.signal);
    const timeoutPromise = Number.isFinite(timeoutMs) && timeoutMs > 0
      ? new Promise<never>((_resolve, reject) => {
        timeout = globalThis.setTimeout(() => {
          const error = new ApiRequestTimeoutError(method, path, timeoutMs);
          controller.abort(error);
          reject(error);
        }, timeoutMs);
      })
      : null;

    try {
      return await (timeoutPromise ? Promise.race([request, timeoutPromise]) : request);
    } finally {
      if (timeout) globalThis.clearTimeout(timeout);
      externalSignal?.removeEventListener('abort', abortFromExternalSignal);
    }
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

const PACKVM_API_ROOT = '/api/v4/packvm';

function packVMLifecyclePost<T>(
  operation: string,
  payload: Record<string, unknown>,
): Promise<T> {
  return apiFetch<T>(`${PACKVM_API_ROOT}/${operation}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function preparePackVM(): Promise<ApiPackVMProvisioningPlan> {
  return packVMLifecyclePost<unknown>('prepare', {}).then(normalizePackVMPlan);
}

export function consentPackVM(
  payload: {
    plan_digest: string;
    ceremony_nonce: string;
    confirmation: string;
    approve_image_download: boolean;
  },
): Promise<ApiPackVMConsent> {
  return packVMLifecyclePost<unknown>('consent', payload).then(normalizePackVMConsent);
}

export function provisionPackVM(
  payload: {consent_id: string; operation_id: string},
): Promise<ApiPackVMOperation> {
  return packVMLifecyclePost<unknown>('provision', payload).then(normalizePackVMOperation);
}

export function fetchPackVMProgress(operationId: string): Promise<ApiPackVMOperation> {
  return apiFetch<unknown>(
    `${PACKVM_API_ROOT}/progress?operation_id=${encodeURIComponent(operationId)}`,
  ).then(normalizePackVMOperation);
}

export function cancelPackVM(operationId: string): Promise<ApiPackVMOperation> {
  return packVMLifecyclePost<unknown>('cancel', {operation_id: operationId})
    .then(normalizePackVMOperation);
}

export function fetchPackVMDoctor(): Promise<ApiPackVMDoctor> {
  return apiFetch<unknown>(`${PACKVM_API_ROOT}/doctor`).then(normalizePackVMDoctor);
}

export function stopPackVM(confirmation: string): Promise<ApiPackVMDoctor> {
  return packVMLifecyclePost<unknown>('stop', {confirmation}).then(normalizePackVMDoctor);
}

export function cleanupPackVM(confirmation: string): Promise<ApiPackVMCleanupResult> {
  return packVMLifecyclePost<unknown>('cleanup', {confirmation}).then(normalizePackVMCleanup);
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
