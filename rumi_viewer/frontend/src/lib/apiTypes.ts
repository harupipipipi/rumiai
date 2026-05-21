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

export type ApiUpdateTarget = 'rumiai' | 'defaultspack';

export interface ApiUpdateInfo {
  target: ApiUpdateTarget;
  current_version: string;
  latest_version: string;
  update_available: boolean;
  release_url: string;
  repo: string;
}

export interface ApiUpdateSettings {
  auto_update: Record<ApiUpdateTarget, boolean>;
  check_interval_hours: number;
  last_checked_at: string | null;
  last_results: Array<Record<string, unknown>>;
  updated_at: string | null;
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

export interface UpdatesResponseData {
  updates: ApiUpdateInfo[];
}

export interface UpdateApplyResponseData {
  target: ApiUpdateTarget;
  current_version: string;
  latest_version: string;
  release_url: string;
  backup_dir: string;
  applied_files: string[];
  skipped_files: string[];
  applied_count: number;
  skipped_count: number;
  restart_required?: boolean;
  routes_reload_recommended?: boolean;
}

export interface ApiStartupNodePort {
  id?: string;
  port_id?: string;
  label?: string;
  display_name?: Record<string, string>;
  direction: 'input' | 'output';
  standards?: string[];
  contracts?: string[];
  multi?: boolean;
  multiple?: boolean;
}

export interface ApiStartupNodeDefinition {
  node_id: string;
  ref?: string;
  title?: string;
  subtitle?: string;
  kind: string;
  component_id?: string;
  component_type?: string;
  metadata?: Record<string, unknown>;
  character?: string;
  display_name?: Record<string, string>;
  ports: ApiStartupNodePort[];
}

export interface ApiStartupPack {
  pack_id: string;
  name: string;
  description: string;
  pack_identity: string;
  available: boolean;
  enabled: boolean;
  approval_issues: string[];
  graphs: Array<{
    graph_id: string;
    display_name?: Record<string, string>;
    description?: Record<string, string>;
    node_count?: number;
    edge_count?: number;
  }>;
  nodes: ApiStartupNodeDefinition[];
}

export interface ApiStartupGraphPort {
  port_key: string;
  node_id: string;
  port_id: string;
  target_node_ref?: string;
  target_port?: ApiStartupNodePort;
  source_node_id: string;
  source_node_ref?: string;
  source_port_id?: string;
  source_port?: ApiStartupNodePort;
  source_ref: string;
}

export interface ApiStartupCatalog {
  version: number;
  packs: ApiStartupPack[];
}

export interface ApiProfileWorkspacePaths {
  profile_id: string;
  root: string;
  profile_file: string;
  user_data_dir: string;
  database_dir?: string;
  database_path: string;
  startup_dir: string;
  flows_dir: string;
  prompts_dir: string;
  ecosystem_dir?: string;
  permissions_dir: string;
  audit_dir?: string;
  snapshots_dir?: string;
}

export interface ApiStartupProfile {
  version: number;
  profile_id: string;
  name: string;
  base_pack: string;
  graph_id: string;
  graph_ports: ApiStartupGraphPort[];
  packs: string[];
  node_overrides: Record<string, string>;
  created_at: number;
  updated_at: number;
  capability_profile_id?: string | null;
  default_graph?: string | null;
  launch_capability_graph?: boolean;
  surfaces?: Record<string, unknown>;
  policy?: Record<string, unknown>;
  permissions?: Record<string, unknown>;
  profile_workspace?: ApiProfileWorkspacePaths;
}

export interface ApiProfileWorkspaceFile {
  name: string;
  path: string;
  size: number;
}

export interface ApiProfileWorkspaceDetail {
  profile: ApiStartupProfile;
  profile_workspace: ApiProfileWorkspacePaths;
  startup_config: Record<string, unknown>;
  flows: ApiProfileWorkspaceFile[];
  prompts: ApiProfileWorkspaceFile[];
  resource_snapshot_manifest: Record<string, unknown>;
  permissions: Record<string, { path: string; exists: boolean }>;
  flow_yaml: {
    path: string | null;
    yaml_content: string;
  };
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
  profile_workspace?: ApiProfileWorkspacePaths;
  created?: boolean;
  updated?: boolean;
  pack_added?: string;
  pack_removed?: string;
  override_set?: { port_key: string; node_id: string };
  override_cleared?: string;
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

export interface StartupProfileCompilePreviewResponseData {
  ok: boolean;
  profile_id: string;
  profile: ApiStartupProfile;
  capability_graph: {
    ok: boolean;
    skipped?: boolean;
    reason?: string | null;
    graph_id?: string | null;
    capability_profile_id?: string | null;
    runtime_profile_key?: string | null;
    runtime_profile?: Record<string, unknown> | null;
    surface_launch_target?: ApiSurfaceLaunchTarget | null;
    diagnostics: ApiCapabilityDiagnostic[];
  };
  surface_launch_target?: ApiSurfaceLaunchTarget | null;
  diagnostics: ApiCapabilityDiagnostic[];
}

export interface StartupProfileDeleteResponseData {
  deleted: boolean;
  deleted_profile_id: string;
  active_profile_id: string | null;
  profile_workspace_orphaned?: boolean;
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

export interface WindowRuntimeSnapshot {
  label: string;
  visible: boolean;
  minimized: boolean;
  focused: boolean;
}

export interface BackgroundControlStatus {
  enabled: boolean;
  app_visible: boolean;
  foreground_window: string | null;
  kernel_running: boolean;
  shutdown_requested: boolean;
  windows: WindowRuntimeSnapshot[];
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
  display_name?: Record<string, string>;
  description?: Record<string, string>;
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

export interface CapabilityGraphResponseData {
  graph: ApiCapabilityGraph;
}

export interface ApiSurfaceLaunchTarget {
  kind: string;
  pack_id: string;
  principal_id?: string;
  surface?: string;
  node_instance_id?: string;
  node_id?: string;
  component_full_id?: string;
  env?: Record<string, string>;
  source?: string;
}

export interface CapabilityGraphCompileResponseData {
  ok: boolean;
  graph_id: string;
  profile_id: string;
  runtime_profile?: Record<string, unknown> | null;
  surface_launch_target?: ApiSurfaceLaunchTarget | null;
  diagnostics: ApiCapabilityDiagnostic[];
}

export interface CapabilityGraphSaveResponseData {
  graph: ApiCapabilityGraph;
  created: boolean;
  path: string;
  diagnostics: ApiCapabilityDiagnostic[];
}

export interface CapabilityProfileCloneResponseData {
  profile: ApiCapabilityProfile;
  created: boolean;
  path: string;
  diagnostics: ApiCapabilityDiagnostic[];
}
