import type {
  ApiResponse,
  PacksResponseData,
  PackToggleResponseData,
  FlowsResponseData,
  ApiFlowDetail,
  FlowCreateResponseData,
  FlowUpdateResponseData,
  FlowDeleteResponseData,
  ApiDashboard,
  ProfileResponseData,
  ApiVersion,
  KernelRestartResponseData,
  OAuthStartResponseData,
  SetupStatusResponseData,
  HealthResponseData,
} from './apiTypes';

// Base URL: empty string means relative path (works with Vite proxy)
const API_BASE_URL =
  (import.meta as ImportMeta & {env?: Record<string, string>}).env?.VITE_API_BASE_URL ?? '';
const API_TOKEN_STORAGE_KEY = 'rumi-api-token';
const API_TOKEN_QUERY_KEY = 'token';

function consumeTokenFromLocation(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    const url = new URL(window.location.href);
    const token = url.searchParams.get(API_TOKEN_QUERY_KEY)?.trim();
    if (!token) {
      return null;
    }

    localStorage.setItem(API_TOKEN_STORAGE_KEY, token);
    url.searchParams.delete(API_TOKEN_QUERY_KEY);
    window.history.replaceState({}, document.title, `${url.pathname}${url.search}${url.hash}`);
    return token;
  } catch {
    return null;
  }
}

export function bootstrapApiTokenFromLocation(): void {
  consumeTokenFromLocation();
}

function getAccessToken(): string | null {
  const tokenFromLocation = consumeTokenFromLocation();
  if (tokenFromLocation) {
    return tokenFromLocation;
  }

  if (typeof window === 'undefined') {
    return null;
  }

  try {
    return localStorage.getItem(API_TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

/**
 * Common fetch wrapper for API calls.
 * - Prepends API_BASE_URL
 * - Sets JSON headers
 * - Parses {success, data, error} envelope
 * - Throws on success===false or non-ok HTTP status
 * - Returns unwrapped `data`
 */
export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${API_BASE_URL}${path}`;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> | undefined),
  };

  const token = getAccessToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    // Try to parse error envelope even on non-ok status
    let errorMessage = `API Error: ${response.status} ${response.statusText}`;
    try {
      const errorBody: ApiResponse<unknown> = await response.json();
      if (errorBody.error) {
        errorMessage = errorBody.error;
      }
    } catch {
      // If JSON parsing fails, use the default error message
    }
    throw new Error(errorMessage);
  }

  const envelope: ApiResponse<T> = await response.json();

  if (!envelope.success) {
    throw new Error(envelope.error || 'Unknown API error');
  }

  return envelope.data as T;
}

// ============================================================
// Dashboard
// ============================================================

export function fetchDashboard(): Promise<ApiDashboard> {
  return apiFetch<ApiDashboard>('/api/panel/dashboard');
}

// ============================================================
// Packs
// ============================================================

export function fetchPacks(): Promise<PacksResponseData> {
  return apiFetch<PacksResponseData>('/api/panel/packs');
}

export function enablePack(id: string): Promise<PackToggleResponseData> {
  return apiFetch<PackToggleResponseData>(
    `/api/panel/packs/${encodeURIComponent(id)}/enable`,
    { method: 'POST' },
  );
}

export function disablePack(id: string): Promise<PackToggleResponseData> {
  return apiFetch<PackToggleResponseData>(
    `/api/panel/packs/${encodeURIComponent(id)}/disable`,
    { method: 'POST' },
  );
}

// ============================================================
// Flows
// ============================================================

export function fetchFlows(): Promise<FlowsResponseData> {
  return apiFetch<FlowsResponseData>('/api/panel/flows');
}

export function fetchFlowDetail(id: string): Promise<ApiFlowDetail> {
  return apiFetch<ApiFlowDetail>(
    `/api/panel/flows/${encodeURIComponent(id)}`,
  );
}

export function createFlow(
  data: { flow_id: string; yaml_content: string; filename?: string },
): Promise<FlowCreateResponseData> {
  return apiFetch<FlowCreateResponseData>('/api/panel/flows', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export function updateFlow(
  id: string,
  data: { yaml_content: string },
): Promise<FlowUpdateResponseData> {
  return apiFetch<FlowUpdateResponseData>(
    `/api/panel/flows/${encodeURIComponent(id)}`,
    {
      method: 'PUT',
      body: JSON.stringify(data),
    },
  );
}

export function deleteFlow(id: string): Promise<FlowDeleteResponseData> {
  return apiFetch<FlowDeleteResponseData>(
    `/api/panel/flows/${encodeURIComponent(id)}`,
    { method: 'DELETE' },
  );
}

// ============================================================
// Settings
// ============================================================

export function fetchProfile(): Promise<ProfileResponseData> {
  return apiFetch<ProfileResponseData>('/api/panel/settings/profile');
}

export function updateProfile(
  data: Record<string, unknown>,
): Promise<ProfileResponseData> {
  return apiFetch<ProfileResponseData>('/api/panel/settings/profile', {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

// ============================================================
// System
// ============================================================

export function fetchVersion(): Promise<ApiVersion> {
  return apiFetch<ApiVersion>('/api/panel/version');
}

export function restartKernel(): Promise<KernelRestartResponseData> {
  return apiFetch<KernelRestartResponseData>('/api/panel/kernel/restart', {
    method: 'POST',
  });
}

// ============================================================
// Setup
// ============================================================

export function fetchSetupStatus(): Promise<SetupStatusResponseData> {
  return apiFetch<SetupStatusResponseData>('/api/setup/status');
}

export function startOAuth(): Promise<OAuthStartResponseData> {
  return apiFetch<OAuthStartResponseData>('/api/setup/oauth/start');
}

// ============================================================
// Health
// ============================================================

export function checkHealth(): Promise<HealthResponseData> {
  return apiFetch<HealthResponseData>('/health');
}
