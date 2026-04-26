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

export interface ApiStartupNodePort {
  port_id: string;
  label: string;
  direction: 'input' | 'output';
  contracts: string[];
  multi: boolean;
}

export interface ApiStartupNodeDefinition {
  node_id: string;
  title: string;
  subtitle: string;
  kind: string;
  character: string;
  ports: ApiStartupNodePort[];
}

export interface ApiStartupSlotSpec {
  slot_id: string;
  label: string;
  description: string;
  contract: string;
  multi: boolean;
  interface_key: string;
  character: string;
}

export interface ApiStartupStandardPack {
  pack_id: string;
  display_name: string;
  description: string;
  pack_identity: string;
  available: boolean;
  runtime_ready: boolean;
  runtime_issues: string[];
  enabled: boolean;
  character: string;
  slots: Array<{
    slot_id: string;
    contract: string;
    label: string;
  }>;
}

export interface ApiStartupSlotCandidate {
  pack_id: string;
  pack_identity: string;
  display_name: string;
  description: string;
  contracts: string[];
  component_types: string[];
  provides: string[];
  character: string;
  enabled: boolean;
  runtime_ready: boolean;
  runtime_issues: string[];
  selected_component_id: string;
}

export interface ApiStartupCatalog {
  version: number;
  start_node: ApiStartupNodeDefinition;
  slot_specs: ApiStartupSlotSpec[];
  standard_packs: ApiStartupStandardPack[];
  slot_candidates: Record<string, ApiStartupSlotCandidate[]>;
}

export interface ApiStartupProfile {
  profile_id: string;
  name: string;
  standard_pack_id: string;
  slots: Record<string, string>;
  created_at: number;
  updated_at: number;
}

export interface FlowsResponseData {
  flows: ApiFlow[];
  count: number;
}

export interface StartupProfilesResponseData {
  profiles: ApiStartupProfile[];
  active_profile_id: string | null;
  last_launched_profile_id: string | null;
  catalog: ApiStartupCatalog;
}

export interface StartupProfileMutationResponseData {
  profile: ApiStartupProfile;
  created?: boolean;
  updated?: boolean;
  duplicated?: boolean;
  activated?: boolean;
  launched?: boolean;
  active_profile_id?: string;
  restart_requested?: boolean;
  handoff?: {
    kind: string;
    reason: string;
    restart_requested: boolean;
    exit_code?: number;
    profile_id?: string;
  };
}

export interface StartupProfileDeleteResponseData {
  deleted: boolean;
  deleted_profile_id: string;
  active_profile_id: string | null;
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
  panel_ready?: boolean;
  runtime_ready?: boolean;
  runtime_status?: 'starting' | 'panel_ready' | 'runtime_ready' | 'error';
  runtime_error?: string | null;
}

export interface HealthResponseData {
  status: 'ok' | 'error';
  needs_setup?: boolean;
  panel_ready?: boolean;
  runtime_ready?: boolean;
  runtime_status?: 'starting' | 'panel_ready' | 'runtime_ready' | 'error';
  runtime_error?: string | null;
}

export interface ApiCapabilityPort {
  id: string;
  label: string;
  direction: 'input' | 'output' | 'bidirectional';
  standards: string[];
  aliases: string[];
  multiple?: boolean;
  required?: boolean;
  display_name?: Record<string, string>;
  description?: Record<string, string>;
}

export interface ApiCapabilityNodeState {
  node_id: string;
  installed: boolean;
  approved: boolean;
  enabled: boolean;
  configured: boolean;
  status: string;
  missing: string[];
  credential_ref?: string | null;
  profile_id?: string;
}

export interface ApiCapabilityNode {
  node_id: string;
  label: string;
  description_label: string;
  kind: string;
  ports: ApiCapabilityPort[];
  bindings: Record<string, unknown>;
  metadata: Record<string, unknown>;
  requirements?: Record<string, unknown>;
  permissions?: Record<string, unknown>;
  state?: ApiCapabilityNodeState;
}

export interface ApiCapabilityProfile {
  profile_id: string;
  label: string;
  description_label: string;
  locale?: string | null;
  default_graph?: string | null;
  default_flow?: string | null;
  permissions: Record<string, unknown>;
  enabled_nodes: string[];
  disabled_nodes: string[];
  node_settings: Record<string, Record<string, unknown>>;
  policy: Record<string, unknown>;
}

export interface ApiCapabilityGraph {
  graph_id: string;
  label: string;
  description_label: string;
  nodes: Array<{id: string; ref: string; display_name?: Record<string, string>; metadata?: Record<string, unknown>}>;
  edges: Array<{id: string; from: string; to: string; kind: string; metadata?: Record<string, unknown>}>;
  metadata: Record<string, unknown>;
}

export interface ApiCapabilityDiagnostic {
  level: string;
  code: string;
  message: string;
  [key: string]: unknown;
}

export interface StartupProfileRelationship {
  launch_time_source_of_truth: string;
  capability_graph_profiles_role: string;
  bridge_policy: string;
  startup_profile_api: string;
}

export interface CapabilityProfilesResponseData {
  profiles: ApiCapabilityProfile[];
  count: number;
  startup_profile_relationship: StartupProfileRelationship;
}

export interface CapabilityNodesResponseData {
  nodes: ApiCapabilityNode[];
  count: number;
}

export interface CapabilityProfileNodesResponseData {
  profile: ApiCapabilityProfile;
  nodes: ApiCapabilityNode[];
  node_state: ApiCapabilityNodeState[];
  palette_nodes: ApiCapabilityNode[];
  count: number;
  palette_count: number;
}

export interface CapabilityGraphsResponseData {
  graphs: ApiCapabilityGraph[];
  count: number;
  diagnostics: ApiCapabilityDiagnostic[];
}

export interface CapabilityGraphCompileResponseData {
  ok: boolean;
  graph_id: string;
  profile_id: string;
  runtime_profile?: Record<string, unknown> | null;
  diagnostics: ApiCapabilityDiagnostic[];
}

export interface CapabilityProfileCloneResponseData {
  profile: ApiCapabilityProfile;
  created: boolean;
  path: string;
  diagnostics: ApiCapabilityDiagnostic[];
}
