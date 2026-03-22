/**
 * Backend → Frontend type transform functions.
 *
 * The backend API returns snake_case types with different field names.
 * These functions convert them to the frontend domain types used by store.ts.
 */

import type {
  ApiPack,
  ApiFlow,
  ApiFlowDetail,
  ApiDashboard,
  ApiProfile,
  ApiVersion,
} from './apiTypes';

import type {
  Pack,
  Flow,
  DashboardData,
  Profile,
  VersionInfo,
} from '../store';

// ============================================================
// Packs
// ============================================================

export function transformPack(api: ApiPack): Pack {
  return {
    id: api.pack_id,
    name: api.name,
    version: api.version,
    type: api.is_core ? 'core' : 'community',
    enabled: api.enabled,
    description: api.description,
    capabilities: [],
    flows: [],
    dependencies: [],
  };
}

export function transformPacks(apiPacks: ApiPack[]): Pack[] {
  return apiPacks.map(transformPack);
}

// ============================================================
// Flows
// ============================================================

export function transformFlow(api: ApiFlow): Flow {
  return {
    id: api.flow_id,
    name: api.name,
    content: '',
  };
}

export function transformFlowDetail(api: ApiFlowDetail): Flow {
  return {
    id: api.flow_id,
    name: api.name,
    content: api.yaml_content,
  };
}

export function transformFlows(apiFlows: ApiFlow[]): Flow[] {
  return apiFlows.map(transformFlow);
}

// ============================================================
// Dashboard
// ============================================================

export function formatUptime(seconds: number | null): string {
  if (seconds === null || seconds === undefined) {
    return '--';
  }
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${minutes}m`;
}

export function transformDashboard(api: ApiDashboard): DashboardData {
  return {
    kernelStatus: api.kernel.status === 'running' ? 'running' : api.kernel.status === 'error' ? 'error' : 'stopped',
    uptime: formatUptime(api.kernel.uptime),
    activePacks: api.packs.enabled,
    registeredFlows: api.flows.total,
    activities: [],
  };
}

// ============================================================
// Profile
// ============================================================

const DEFAULT_AVATAR = 'https://picsum.photos/seed/rumi-av1/128/128';

export function transformProfile(api: ApiProfile): Profile {
  return {
    username: api.username,
    language: api.language,
    avatar: api.icon || DEFAULT_AVATAR,
    job: api.occupation || '',
    connected: true,
  };
}

// ============================================================
// Version
// ============================================================

export function transformVersion(api: ApiVersion): VersionInfo {
  return {
    app: 'v1.10.0',
    kernel: api.kernel_version,
    python: api.python_version,
    launcher: 'unknown',
    docker: {
      installed: false,
      version: '',
      type: '',
    },
  };
}
