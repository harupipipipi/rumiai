import type {
  ApiResponse,
  DashboardResponse,
  ActivityResponse,
  PacksResponse,
  PackDetailResponse,
  FlowsResponse,
  FlowDetailResponse,
  ProfileResponse,
  VersionResponse,
  SetupStatusResponse,
  HealthResponse,
} from './apiTypes';

// Base URL: empty string means relative path (works with Vite proxy)
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

/**
 * Common fetch wrapper for API calls.
 * - Prepends API_BASE_URL
 * - Sets JSON headers
 * - Throws on non-ok responses
 * - Placeholder for future OAuth token injection
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

  // TODO: OAuth token injection (Phase C)
  // const token = getAccessToken();
  // if (token) {
  //   headers['Authorization'] = `Bearer ${token}`;
  // }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const errorBody = await response.text().catch(() => '');
    throw new Error(
      `API Error: ${response.status} ${response.statusText} - ${errorBody}`,
    );
  }

  return response.json() as Promise<T>;
}

// ============================================================
// Dashboard
// ============================================================

export function fetchDashboard(): Promise<DashboardResponse> {
  return apiFetch<DashboardResponse>('/api/panel/dashboard');
}

export function fetchActivity(limit = 20): Promise<ActivityResponse> {
  return apiFetch<ActivityResponse>(`/api/panel/activity?limit=${limit}`);
}

// ============================================================
// Packs
// ============================================================

export function fetchPacks(): Promise<PacksResponse> {
  return apiFetch<PacksResponse>('/api/packs');
}

export function fetchPackDetail(id: string): Promise<PackDetailResponse> {
  return apiFetch<PackDetailResponse>(`/api/packs/${encodeURIComponent(id)}`);
}

export function enablePack(id: string): Promise<ApiResponse<null>> {
  return apiFetch<ApiResponse<null>>(
    `/api/panel/packs/${encodeURIComponent(id)}/enable`,
    { method: 'POST' },
  );
}

export function disablePack(id: string): Promise<ApiResponse<null>> {
  return apiFetch<ApiResponse<null>>(
    `/api/panel/packs/${encodeURIComponent(id)}/disable`,
    { method: 'POST' },
  );
}

// ============================================================
// Flows
// ============================================================

export function fetchFlows(): Promise<FlowsResponse> {
  return apiFetch<FlowsResponse>('/api/flows');
}

export function fetchFlowDetail(id: string): Promise<FlowDetailResponse> {
  return apiFetch<FlowDetailResponse>(
    `/api/panel/flows/${encodeURIComponent(id)}`,
  );
}

export function createFlow(
  data: Record<string, unknown>,
): Promise<FlowDetailResponse> {
  return apiFetch<FlowDetailResponse>('/api/panel/flows', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export function updateFlow(
  id: string,
  data: Record<string, unknown>,
): Promise<FlowDetailResponse> {
  return apiFetch<FlowDetailResponse>(
    `/api/panel/flows/${encodeURIComponent(id)}`,
    {
      method: 'PUT',
      body: JSON.stringify(data),
    },
  );
}

export function deleteFlow(id: string): Promise<ApiResponse<null>> {
  return apiFetch<ApiResponse<null>>(
    `/api/panel/flows/${encodeURIComponent(id)}`,
    { method: 'DELETE' },
  );
}

export function runFlow(
  id: string,
): Promise<ApiResponse<{ status: string }>> {
  return apiFetch<ApiResponse<{ status: string }>>(
    `/api/flows/${encodeURIComponent(id)}/run`,
    { method: 'POST' },
  );
}

// ============================================================
// Settings
// ============================================================

export function fetchProfile(): Promise<ProfileResponse> {
  return apiFetch<ProfileResponse>('/api/panel/settings/profile');
}

export function updateProfile(
  data: Record<string, unknown>,
): Promise<ProfileResponse> {
  return apiFetch<ProfileResponse>('/api/panel/settings/profile', {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

// ============================================================
// System
// ============================================================

export function fetchVersion(): Promise<VersionResponse> {
  return apiFetch<VersionResponse>('/api/panel/version');
}

export function restartKernel(): Promise<ApiResponse<null>> {
  return apiFetch<ApiResponse<null>>('/api/panel/kernel/restart', {
    method: 'POST',
  });
}

// ============================================================
// Setup
// ============================================================

export function fetchSetupStatus(): Promise<SetupStatusResponse> {
  return apiFetch<SetupStatusResponse>('/api/setup/status');
}

export function startOAuth(): Promise<ApiResponse<{ url: string }>> {
  return apiFetch<ApiResponse<{ url: string }>>('/api/setup/oauth/start');
}

// ============================================================
// Health
// ============================================================

export function checkHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('/health');
}
