export type RuntimeProviderKind = "auto" | "linux_native" | "windows_wsl" | "mac_lima" | "docker" | string;

export type RuntimeStatusKind =
  | "ready"
  | "available"
  | "unavailable"
  | "needs_setup"
  | "installing"
  | "updating"
  | "failed"
  | "error";

export type RuntimeIssueSeverity = "info" | "warning" | "error";

export type RuntimeDoctorIssue = {
  code: string;
  message: string;
  severity?: RuntimeIssueSeverity;
  detail?: string;
  remediation?: string;
  provider_id?: string;
};

export type RuntimeIsolationFacts = {
  mode?: string;
  vm?: boolean;
  container?: boolean;
  host_process_namespace?: boolean;
  host_filesystem_shared?: boolean;
  host_network_shared?: boolean;
  summary?: string;
  warnings?: string[];
};

export type RuntimeProviderStatus = {
  provider_id: RuntimeProviderKind;
  label?: string;
  status: RuntimeStatusKind;
  available?: boolean;
  installed?: boolean;
  ready?: boolean;
  selected?: boolean;
  managed?: boolean;
  platform?: string;
  version?: string | null;
  guest_protocol?: string | number | null;
  missing?: RuntimeDoctorIssue[];
  isolation?: RuntimeIsolationFacts;
  diagnostics?: Record<string, unknown>;
  message?: string;
};

export type RuntimeProvidersResponse = {
  providers: RuntimeProviderStatus[];
  selected_provider_id?: string | null;
  default_provider_id?: string | null;
  runtime_version?: string | null;
  guest_protocol?: string | number | null;
};

export type RuntimeDoctorResult = {
  status: RuntimeStatusKind;
  providers?: RuntimeProviderStatus[];
  selected_provider_id?: string | null;
  missing?: RuntimeDoctorIssue[];
  message?: string;
  diagnostics?: Record<string, unknown>;
  generated_at?: string;
};

export type RuntimeOperationStatus =
  | "planned"
  | "downloading"
  | "verified"
  | "installing"
  | "reboot_pending"
  | "starting_agent"
  | "health_checking"
  | "completed"
  | "failed"
  | "cancelled";

export type RuntimeOperation = {
  operation_id: string;
  status: RuntimeOperationStatus;
  step?: string;
  message?: string;
  progress?: number;
  reboot_required?: boolean;
  error?: RuntimeDoctorIssue | string | null;
  provider_id?: string | null;
  updated_at?: string;
};

export type SandboxTemplateKind = "pack" | "coding" | "desktop" | "tool" | "unknown";

export type SandboxTemplate = {
  template_id: string;
  name?: string;
  description?: string;
  kind?: SandboxTemplateKind;
  trust_level?: "builtin" | "user" | "unknown";
  source_pack_id?: string;
  source_template_ids?: string[];
  default_provider_id?: string | null;
  provider_requirements?: string[];
  capabilities?: string[];
  network_policy?: {
    summary?: string;
    default?: string;
    allowed?: string[];
  };
  workspace_access?: {
    summary?: string;
    mode?: string;
  };
  provisioning?: DesktopProvisioning;
  isolation?: RuntimeIsolationFacts;
};

export type SandboxInstance = {
  sandbox_id: string;
  template_id?: string;
  name?: string;
  status: SandboxState;
  state?: SandboxState;
  provider_id?: string | null;
  created_at?: string;
  updated_at?: string;
};

export type SandboxState =
  | "creating"
  | "provisioning"
  | "starting"
  | "ready"
  | "busy"
  | "stopping"
  | "stopped"
  | "failed"
  | "destroying"
  | "destroyed"
  | "unknown";

export type DesktopStatus =
  | "creating"
  | "provisioning"
  | "starting"
  | "running"
  | "stopped"
  | "failed"
  | "destroying"
  | "destroyed"
  | "unknown";

export type DesktopResolution = {
  width: number;
  height: number;
};

export type DesktopControlState = {
  holder?: "ai" | "human" | "none" | "unknown";
  lease_expires_at?: string | null;
  conflict_code?: string | null;
  message?: string | null;
};

export type DesktopRules = {
  role?: string | null;
  instructions?: string;
  rule_ids?: string[];
};

export type DesktopAccessPolicy = {
  mode?: "owner_only" | "shared_link" | "key_required" | "request_required";
  key_required?: boolean;
  request_required?: boolean;
  key_hint?: string | null;
  link_enabled?: boolean;
};

export type DesktopProvisioning = {
  packages?: Array<{ name?: string; version?: string | null; source?: string | null }>;
  apps?: string[];
  mcp_servers?: string[];
  status?: string;
  default?: boolean;
};

export type DesktopFrameMetadata = {
  frame_seq?: number | null;
  width?: number | null;
  height?: number | null;
  mime_type?: string | null;
  captured_at?: string | null;
  age_ms?: number | null;
  error?: string | null;
};

export type DesktopInstance = {
  seat_id: string;
  sandbox_id?: string | null;
  name: string;
  status: DesktopStatus;
  provider_id?: string | null;
  provider_label?: string | null;
  template_id?: string | null;
  resolution?: DesktopResolution | null;
  frame?: DesktopFrameMetadata | null;
  assigned_agent?: string | null;
  role?: string | null;
  rules?: DesktopRules | string[] | null;
  access_policy?: DesktopAccessPolicy | null;
  provisioning?: DesktopProvisioning | null;
  control?: DesktopControlState | null;
  isolation?: RuntimeIsolationFacts | null;
  network_policy?: {
    summary?: string;
    default?: string;
  } | null;
  workspace?: {
    workspace_id?: string | null;
    label?: string | null;
    access?: string | null;
  } | null;
  last_error?: RuntimeDoctorIssue | string | null;
  created_at?: string;
  updated_at?: string;
};

export type DesktopStarter = "empty" | "browser_url" | "terminal";

export type CreateDesktopRequest = {
  name: string;
  template_id: string;
  provider_id?: string | null;
  resolution: DesktopResolution;
  starter: DesktopStarter;
  browser_url?: string;
  workspace_id?: string | null;
  workspace_access?: "none" | "read_only" | "overlay" | null;
  assigned_agent?: string | null;
  role?: string | null;
  rules?: DesktopRules | string[] | null;
  access?: {
    mode?: "owner_only" | "shared_link" | "key_required" | "request_required";
    access_key?: string;
    request_required?: boolean;
  };
  provisioning?: DesktopProvisioning | null;
  request_id?: string;
};

export type DesktopFrameQuality = "grid" | "focus" | "control";

export type DesktopFrameResult =
  | {
      status: "frame";
      seat_id: string;
      frame_seq: number;
      width: number;
      height: number;
      mime_type: string;
      blob: Blob;
      captured_at?: string | null;
    }
  | {
      status: "not_modified";
      seat_id: string;
      after_seq: number | null;
    };

export type DesktopFrameView = {
  frame_seq: number;
  width: number;
  height: number;
  mime_type: string;
  object_url: string;
  captured_at?: string | null;
  received_at: number;
};

export type DesktopControlLeaseGrant = {
  seat_id: string;
  lease_id?: string;
  lease_token: string;
  expires_at: string;
  holder?: "human" | "unknown";
};

export type DesktopControlLeaseRenewal = {
  seat_id: string;
  lease_id?: string;
  expires_at: string;
  acquired_at?: number | string;
  owner_id?: string;
};

export type DesktopControlLease = DesktopControlLeaseGrant;

export type DesktopInputRequest =
  | {
      action: "click";
      x: number;
      y: number;
      button?: "left" | "middle" | "right";
      lease_token: string;
      access_key?: string;
      client_action_id?: string;
      request_id?: string;
    }
  | {
      action: "key";
      key: string;
      lease_token: string;
      access_key?: string;
      client_action_id?: string;
      request_id?: string;
    }
  | {
      action: "type_text";
      text: string;
      lease_token: string;
      access_key?: string;
      client_action_id?: string;
      request_id?: string;
    }
  | {
      action: "scroll";
      x: number;
      y: number;
      delta_x?: number;
      delta_y?: number;
      lease_token: string;
      access_key?: string;
      client_action_id?: string;
      request_id?: string;
    };

const runtimeStatuses: RuntimeStatusKind[] = [
  "ready",
  "available",
  "unavailable",
  "needs_setup",
  "installing",
  "updating",
  "failed",
  "error",
];

const sandboxStates: SandboxState[] = [
  "creating",
  "provisioning",
  "starting",
  "ready",
  "busy",
  "stopping",
  "stopped",
  "failed",
  "destroying",
  "destroyed",
  "unknown",
];

const desktopStatuses: DesktopStatus[] = [
  "creating",
  "provisioning",
  "starting",
  "running",
  "stopped",
  "failed",
  "destroying",
  "destroyed",
  "unknown",
];

export function normalizeRuntimeStatus(value: unknown): RuntimeStatusKind {
  const status = String(value || "").toLowerCase();
  return runtimeStatuses.includes(status as RuntimeStatusKind) ? status as RuntimeStatusKind : "unavailable";
}

export function normalizeSandboxState(value: unknown): SandboxState {
  const state = String(value || "").toLowerCase();
  if (state === "error") return "failed";
  return sandboxStates.includes(state as SandboxState) ? state as SandboxState : "unknown";
}

export function normalizeDesktopStatus(value: unknown): DesktopStatus {
  const raw = String(value || "").toLowerCase();
  if (raw === "ready" || raw === "busy") return "running";
  if (desktopStatuses.includes(raw as DesktopStatus)) return raw as DesktopStatus;
  const status = normalizeSandboxState(raw);
  return desktopStatuses.includes(status as DesktopStatus) ? status as DesktopStatus : "unknown";
}
