/**
 * API Response type definitions.
 *
 * Currently re-exports types from store.ts.
 * When the backend API is finalized, these may diverge from store types,
 * and a mapping/transform layer will be added.
 */

import type {
  Pack,
  Flow,
  DashboardData,
  Activity,
  Profile,
  VersionInfo,
} from '../store';

// Re-export domain types for use by API consumers
export type { Pack, Flow, DashboardData, Activity, Profile, VersionInfo };

// ============================================================
// Generic API wrapper
// ============================================================

/** Generic API response envelope for future error handling */
export interface ApiResponse<T> {
  ok: boolean;
  data: T;
  error?: string;
}

// ============================================================
// Endpoint-specific response types
// ============================================================

export type DashboardResponse = DashboardData;
export type ActivityResponse = Activity[];
export type PacksResponse = Pack[];
export type PackDetailResponse = Pack;
export type FlowsResponse = Flow[];
export type FlowDetailResponse = Flow;
export type ProfileResponse = Profile;
export type VersionResponse = VersionInfo;

export interface SetupStatusResponse {
  setupDone: boolean;
  currentStep: string;
}

export interface HealthResponse {
  status: 'ok' | 'error';
  timestamp: string;
}
