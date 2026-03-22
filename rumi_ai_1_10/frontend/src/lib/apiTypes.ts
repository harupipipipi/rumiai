/**
 * API Type definitions — aligned with backend APIResponse envelope.
 *
 * Backend always returns: { success: boolean, data: T | null, error: string | null }
 * The apiFetch wrapper unwraps this envelope and returns data directly.
 */

// ============================================================
// Generic API envelope
// ============================================================

export interface ApiResponse<T> {
  success: boolean;
  data: T | null;
  error: string | null;
}

// ============================================================
// Backend data types (as returned inside envelope's `data`)
// ============================================================

/** GET /api/panel/packs → data.packs[] */
export interface ApiPack {
  pack_id: string;
  name: string;
  version: string;
  description: string;
  is_core: boolean;
  enabled: boolean;
}

/** GET /api/panel/flows → data.flows[] */
export interface ApiFlow {
  flow_id: string;
  name: string;
  pack_id: string;
  filename: string;
}

/** GET /api/panel/flows/{id} → data */
export interface ApiFlowDetail {
  flow_id: string;
  name: string;
  pack_id: string;
  filename: string;
  yaml_content: string;
}

/** GET /api/panel/dashboard → data */
export interface ApiDashboard {
  packs: { total: number; enabled: number; disabled: number };
  flows: { total: number };
  kernel: { status: string; uptime: number | null };
  profile: { username: string; language: string; icon: string | null } | null;
}

/** GET /api/panel/settings/profile → data.profile */
export interface ApiProfile {
  username: string;
  language: string;
  icon: string | null;
  occupation: string | null;
}

/** GET /api/panel/version → data */
export interface ApiVersion {
  kernel_version: string;
  python_version: string;
  platform: string;
  platform_release: string;
}

// ============================================================
// Endpoint-specific response data shapes (inside envelope)
// ============================================================

export interface PacksResponseData {
  packs: ApiPack[];
  count: number;
}

export interface PackToggleResponseData {
  pack_id: string;
  enabled: boolean;
}

export interface FlowsResponseData {
  flows: ApiFlow[];
  count: number;
}

export interface FlowCreateResponseData {
  flow_id: string;
  filename: string;
  created: boolean;
}

export interface FlowUpdateResponseData {
  flow_id: string;
  filename: string;
  updated: boolean;
}

export interface FlowDeleteResponseData {
  flow_id: string;
  deleted: boolean;
}

export interface ProfileResponseData {
  profile: ApiProfile;
  updated?: boolean;
}

export interface KernelRestartResponseData {
  restarting: boolean;
  message: string;
}

export interface OAuthStartResponseData {
  authorize_url: string;
  state: string;
}

export interface SetupStatusResponseData {
  needs_setup: boolean;
  reason?: string;
}

export interface HealthResponseData {
  status: 'ok' | 'error';
  needs_setup?: boolean;
}
