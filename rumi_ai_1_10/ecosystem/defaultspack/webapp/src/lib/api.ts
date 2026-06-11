import type { ToolPreviewItem } from "../components/ToolPreview";

const DEFAULTSPACK_CSRF_STORAGE_KEY = "rumi-defaultspack-csrf";

export type ChatContentBlock = {
  type?: string;
  text?: string;
  [key: string]: unknown;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant" | string;
  content: string | ChatContentBlock[];
  raw_text?: string | null;
  created_at: number;
  conversation_id: string;
  parent_id?: string | null;
  children_ids?: string[];
  sequence_number?: number;
  finish_reason?: string | null;
  usage?: Record<string, number> | null;
  widget?: Record<string, unknown> | null;
  metadata?: Record<string, unknown> | null;
  events?: ChatActivityEvent[] | null;
  tool_logs?: ToolLogEntry[] | null;
  model?: string | null;
};

export type ChatAttachment = {
  name: string;
  content?: string;
  dataUrl?: string;
  size: number;
  type?: string;
  truncated?: boolean;
  source?: "local_file" | "workspace";
  sourcePath?: string;
};

export type BrowserScreenshot = {
  id: string;
  run_id: string;
  tool_call_id?: string | null;
  tool_name?: string;
  mime_type?: string;
  data_url: string;
  action?: string;
  image_size?: { width?: number; height?: number };
  click_marker?: { x?: number; y?: number; screen_x?: number; screen_y?: number; coordinate_space?: string };
  marker?: { x?: number; y?: number; screen_x?: number; screen_y?: number; coordinate_space?: string };
  drag_marker?: {
    from?: { x?: number; y?: number; screen_x?: number; screen_y?: number; coordinate_space?: string };
    to?: { x?: number; y?: number; screen_x?: number; screen_y?: number; coordinate_space?: string };
  };
  target_window?: Record<string, unknown>;
};

export type CodingContextEntry = {
  name: string;
  path: string;
  is_dir: boolean;
  size: number;
};

export type CodingGitStatus = {
  branch?: string;
  clean?: boolean;
  staged?: string[];
  modified?: string[];
  untracked?: string[];
  porcelain?: string;
  [key: string]: unknown;
};

export type CodingContextResponse = {
  branch: string | null;
  root_folder: string | null;
  workspace_id?: string | null;
  workspace_root?: string | null;
  directory?: string;
  files: string[];
  entries?: CodingContextEntry[];
  git?: CodingGitStatus | null;
};

export type CodingBranchResponse = {
  branch: string;
  branches: string[];
  remote?: string | null;
  dirty?: boolean;
  switched?: boolean;
  created?: boolean;
  output?: string;
  workspace_id?: string | null;
  workspace_root?: string | null;
};

export type CodingWorkspaceRecord = {
  workspace_id: string;
  label: string;
  root_path: string;
  trusted?: boolean;
  trust_granted_at?: string | null;
  last_used_at?: string | null;
  metadata?: Record<string, unknown>;
};

export type CodingWorkspacesResponse = {
  workspaces: CodingWorkspaceRecord[];
  selected_workspace_id?: string | null;
};

export type DirectorySelectionResponse = {
  path: string | null;
  cancelled?: boolean;
};

export type ChatGroupStorageResponse = {
  root_path: string;
  rumi_data_path: string;
  chat_store_path: string;
};

export type CodingApprovalRequest = {
  request_id: string;
  operation: string;
  risk_level: string;
  args_hash?: string;
  details?: Record<string, unknown>;
  created_at?: number;
  expires_at?: number;
  status: string;
  display_summary?: string;
};

export type CodingApprovalDecision = {
  request_id: string;
  status: string;
  approved: boolean;
  token?: string;
  expires_at?: number | null;
  reason?: string;
};

export type CodingCheckpoint = {
  snapshot_id: string;
  path?: string;
  kind?: string;
  files?: string[];
  created_at?: string;
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
};

export type CodingDiffResponse = {
  diff: string;
  stat?: string;
  files?: string[];
  files_changed?: number;
  workspace_id?: string | null;
  workspace_root?: string | null;
};

export type CodingTerminalResponse = {
  command: string;
  approval_required?: boolean;
  approval_request_id?: string;
  operation?: string;
  risk_level?: string;
  args_hash?: string;
  expires_at?: number;
  display_summary?: string;
  classification?: string;
  risk_reasons?: string[];
  risk?: Record<string, unknown>;
  exit_code?: number | null;
  stdout?: string;
  stderr?: string;
  workspace_id?: string | null;
  workspace_root?: string | null;
};

export type BrowserArtifact = {
  artifact_id: string;
  session_id: string;
  action: string;
  created_at: string;
  url?: string | null;
  text?: string | null;
  console?: unknown[];
  screenshot?: {
    path?: string;
    data_url?: string;
    mime_type?: string;
    image_size?: { width?: number; height?: number };
  } | null;
  metadata?: Record<string, unknown>;
};

export type McpServerRecord = {
  server_id: string;
  name?: string;
  server_name?: string;
  transport?: string;
  status?: string;
  connected?: boolean;
  tools?: unknown[];
  permissions?: Record<string, unknown>;
  config?: Record<string, unknown>;
};

export type CodingAgentSession = {
  session_id: string;
  status: string;
  task?: string;
  agents?: Array<Record<string, unknown>>;
  shared_context?: Record<string, unknown>;
  agent_contexts?: Record<string, unknown>;
  [key: string]: unknown;
};

export type CompanyAgent = {
  id?: string;
  agent_id: string;
  role_key?: string;
  agent_name?: string;
  display_name?: string;
  model?: string;
  allowed_tools?: string[];
  context_limit?: number;
  aliases?: string[];
  system_prompt?: string;
  status?: string;
  metadata?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
};

export type CompanyChannel = {
  id: string;
  name?: string;
  description?: string;
  visibility?: string;
  members?: string[];
  mentions?: boolean;
  append_only?: boolean;
  message_count?: number;
  last_message_at?: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
};

export type CompanyMessage = {
  id: string;
  company_id: string;
  channel_id: string;
  sender_id: string;
  content: string;
  mentions?: string[];
  task_ids?: string[];
  metadata?: Record<string, unknown>;
  handoff?: {
    target_agent_id?: string;
    reason?: string;
  };
  attachments?: Array<{
    name?: string;
    path?: string;
    url?: string;
    mime_type?: string;
    size?: number;
  }>;
  created_at?: string;
  updated_at?: string;
};

export type CompanyTask = {
  id: string;
  company_id: string;
  title: string;
  description?: string;
  target_agent_ids?: string[];
  source?: string;
  status?: string;
  dispatches?: Array<Record<string, unknown>>;
  metadata?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
};

export type CompanyRunLink = {
  link_id: string;
  company_id: string;
  task_id?: string | null;
  thread_id?: string | null;
  message_id?: string | null;
  agent_id: string;
  run_id: string;
  status: string;
  heartbeat_at?: string | null;
  agent_run?: {
    status?: string | null;
    model?: string | null;
    result_preview?: string;
    error?: string | null;
    conversation?: CompanyRunConversationMessage[];
    updated_at?: string | null;
  };
  metadata?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
};

export type CompanyRunConversationMessage = {
  role: string;
  label?: string;
  content: string;
  is_error?: boolean;
};

export type CompanyInboxItem = {
  inbox_id: string;
  company_id: string;
  agent_id: string;
  message_id?: string | null;
  task_id?: string | null;
  run_id?: string | null;
  kind: string;
  status: string;
  priority?: string;
  content: string;
  metadata?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
};

export type CompanyInboundRoute = {
  id: string;
  provider?: string;
  source?: string;
  channel_id?: string;
  enabled?: boolean;
  metadata?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
};

export type CompanyRecord = {
  id: string;
  name: string;
  description?: string;
  status?: string;
  conversation_group_id?: string;
  settings?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  agents?: Record<string, CompanyAgent> | CompanyAgent[];
  channels?: Record<string, CompanyChannel> | CompanyChannel[];
  messages?: Record<string, CompanyMessage> | CompanyMessage[];
  tasks?: Record<string, CompanyTask> | CompanyTask[];
  inbound_routes?: Record<string, CompanyInboundRoute> | CompanyInboundRoute[];
  agent_count?: number;
  channel_count?: number;
  message_count?: number;
  task_count?: number;
  created_at?: string;
  updated_at?: string;
};

export type CompanyStatusResponse = {
  bootstrapped: boolean;
  company_id: string;
  conversation_id?: string;
  company?: CompanyRecord | null;
  runtime?: Record<string, number>;
  storage_file?: string;
};

export type P2PSettings = {
  enabled?: boolean;
  bind_host?: string;
  bind_port?: number;
  lan_discovery?: boolean;
  internet_relay?: boolean;
  store_path?: string;
  envelope_ttl_seconds?: number;
  replay_ttl_seconds?: number;
  pairing_ttl_seconds?: number;
  [key: string]: unknown;
};

export type P2PIdentity = {
  node_id: string;
  fingerprint?: string;
  label?: string;
  node_secret?: string;
  created_at?: number;
  updated_at?: number;
  [key: string]: unknown;
};

export type P2PPeer = {
  peer_id: string;
  fingerprint?: string;
  hmac_secret?: string;
  status?: "pending" | "approved" | "blocked" | string;
  capabilities?: string[];
  allowed_company_ids?: string[];
  label?: string;
  metadata?: Record<string, unknown>;
  created_at?: number;
  updated_at?: number;
};

export type P2PPairing = {
  pairing_id: string;
  code: string;
  status: "pending" | "accepted" | "rejected" | "expired" | string;
  expires_at: number;
  created_at: number;
  peer_id?: string;
  peer_fingerprint?: string;
  peer_label?: string;
  capabilities?: string[];
  allowed_company_ids?: string[];
  accepted_at?: number;
  rejected_at?: number;
  reason?: string;
};

export type P2PStatusResponse = {
  p2p: P2PSettings;
  peer_count: number;
  approved_peer_count: number;
};

export type ConversationListOptions = {
  tag?: string;
  tags?: string[];
  is_starred?: boolean;
  is_pinned?: boolean;
  is_archived?: boolean;
  company_id?: string;
  workspace_id?: string;
  conversation_kind?: string;
  limit?: number;
  offset?: number;
};

export type CompactConversationOptions = {
  protect_last_messages?: number;
  start_message_id?: string;
  end_message_id?: string;
  reason?: string;
  instruction?: string;
  approved?: boolean;
  approval_token?: string;
};

export type CompactConversationResult = {
  conversation?: Conversation;
  summary_message?: ChatMessage | null;
  deleted_message_ids?: string[];
  deleted_count?: number;
  protect_last_messages?: number;
  message?: string;
  mode?: string;
  compactable?: boolean;
  trim_plan?: Record<string, unknown>;
};

export type OperationsCompanyRole = {
  agent_id: string;
  role_key: string;
  agent_name: string;
  display_name: string;
  model?: string;
  allowed_tools?: string[];
  context_limit?: number;
};

export type OperationsCompanyStatus = {
  profile_id: string;
  bootstrapped: boolean;
  org_id?: string | null;
  conversation_id?: string | null;
  org?: {
    org_id: string;
    name: string;
    status: string;
    members?: Record<string, unknown>;
    member_count?: number;
    recent_messages?: unknown[];
  } | null;
  schedules?: Array<Record<string, unknown>>;
  manifest: {
    name?: string;
    non_stop?: boolean;
    can_run_24_7?: boolean;
    roles?: OperationsCompanyRole[];
    scheduler?: Record<string, unknown>;
    model_self_selection?: { allowlist?: string[] };
    tool_policy?: { allowlist?: string[]; denylist?: string[]; role_overrides?: Record<string, string[]> };
  };
};

export type MimoCodingCompanyStatus = OperationsCompanyStatus;

export type ChatActivityEvent = {
  type: string;
  message?: string;
  phase?: string;
  timestamp?: number | string;
  tool_name?: string;
  tool_call_id?: string;
  model?: string;
  [key: string]: unknown;
};

export type ToolLogEntry = {
  tool_name?: string;
  tool_call_id?: string;
  arguments?: Record<string, unknown>;
  result?: unknown;
  timestamp?: number | string;
  [key: string]: unknown;
};

export function conversationArtifactFileUrl(conversationId: string, path: string): string {
  return `/api/chat/conversations/${encodeURIComponent(conversationId)}/artifact-file?path=${encodeURIComponent(path)}`;
}

export type ModelProfile = {
  profile_id: string;
  display_name: string;
  provider_id?: string;
  provider_display_name?: string;
  model_id?: string;
  type?: string;
  qualified_model_id?: string;
  max_context?: number;
  max_context_tokens?: number;
  supports_thinking?: boolean;
  supports_vision?: boolean;
  supports_image_input?: boolean;
  supports_tool_calling?: boolean;
  supports_fast?: boolean;
  thinking_levels?: string[];
  default_thinking_level?: string | null;
  speed_tier?: string;
  quality_tier?: string;
  knowledge_level?: number;
  knowledge_band?: string;
  cost_tier?: string;
  capability_tags?: string[];
  recommended_roles?: string[];
  allowed_roles?: string[];
  availability?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  defaults?: Record<string, unknown>;
  pricing?: Record<string, unknown>;
  name_collision?: boolean;
  provider_count_for_model_name?: number;
  disambiguated_name?: string;
  same_model_across_providers_key?: string;
  local?: boolean;
};

export type ModelCandidate = {
  provider_id: string;
  model_id: string;
  label?: string;
  profile_id?: string;
};

export type ModelAvailabilityAfterKeySave =
  | { status: "models_available"; profiles: ModelProfile[]; selected_profile_id: string }
  | { status: "route_required"; provider_id: string; api_id: string; candidate_models: ModelCandidate[]; reason: string };

export type ModelCommandCandidate = {
  profile_id: string;
  display_name: string;
  subtitle?: string;
  provider_id?: string;
  provider_display_name?: string;
  model_id?: string;
  qualified_model_id?: string;
  requires_api_key?: boolean;
  api_key_required?: boolean;
  api_key_configured?: boolean;
  configured?: boolean;
  availability?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
};

export type ModelSearchItem = ModelCommandCandidate & {
  label?: string;
  supports_vision?: boolean;
  supports_image_input?: boolean;
  supports_tool_calling?: boolean;
  supports_thinking?: boolean;
  supports_fast?: boolean;
  speed_tier?: string;
  quality_tier?: string;
  cost_tier?: string;
  knowledge_level?: number;
  capability_tags?: string[];
  recommended_roles?: string[];
  notes?: string;
  score?: number;
};

export type ModelSearchResponse = {
  models: ModelSearchItem[];
  filters_applied: Record<string, unknown>;
};

export type ConversationSteerItem = {
  id: string;
  prompt: string;
  target_type?: string;
  target_id?: string;
  conversation_id?: string;
  status: string;
  visible?: boolean;
  auto_send?: boolean;
  created_at?: string;
  updated_at?: string;
  error?: string;
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
};

export type ConversationSteerResponse =
  | ConversationSteerItem
  | {
    items?: ConversationSteerItem[];
    processed?: ConversationSteerItem[];
    cancelled?: boolean;
    item?: ConversationSteerItem | null;
  };

export type Conversation = {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
  model: string;
  system_prompt_id?: string | null;
  agent_id?: string | null;
  parent_conversation_id?: string | null;
  child_conversation_ids?: string[];
  conversation_kind?: string;
  group_id?: string | null;
  metadata?: Record<string, unknown> | null;
  tags: string[];
  is_starred: boolean;
  is_pinned?: boolean;
  pinned_at?: number | string | null;
  pin_scope?: "global" | "group" | "company" | string;
  is_archived: boolean;
  current_node_id?: string | null;
  messages: ChatMessage[];
};

export type ConversationSearchMatch = {
  message_id?: string;
  role?: string;
  created_at?: number;
  snippet: string;
  exact?: boolean;
  score?: number;
};

export type ConversationSearchResult = {
  conversation_id: string;
  title: string;
  created_at?: number;
  updated_at?: number;
  is_starred?: boolean;
  is_archived?: boolean;
  score?: number;
  exact_score?: number;
  semantic_score?: number;
  match_count?: number;
  matches?: ConversationSearchMatch[];
};

export type ConversationSearchOptions = {
  date_filter?: "all" | "today" | "7d" | "30d";
  is_starred?: boolean;
  is_archived?: boolean;
  role?: "all" | "user" | "assistant";
  limit?: number;
  offset?: number;
};

export type SystemPromptRecord = {
  id: string;
  name: string;
  description?: string;
  body: string;
  content?: string;
  tags?: string[];
  variables?: Array<Record<string, unknown>>;
  metadata?: Record<string, unknown>;
  source?: string;
  source_pack_id?: string;
  read_only?: boolean;
  active?: boolean;
  created_at?: string;
  updated_at?: string;
  char_count?: number;
  token_estimate?: number;
  variable_count?: number;
};

export type SystemPromptListResponse = {
  prompts: SystemPromptRecord[];
  active_id?: string;
  active_content?: string;
  inline_content?: string;
  prompt?: SystemPromptRecord;
  deleted?: boolean;
};

export type SidebarCategory = "tool" | "widget" | "system" | "integration" | "capability";

export type SidebarFieldOption = {
  value: string | number | boolean;
  label: string;
  provider_id?: string;
  provider_display_name?: string;
  model_id?: string;
  qualified_model_id?: string;
  configured?: boolean;
  local?: boolean;
  supports_vision?: boolean;
  supports_image_input?: boolean;
  supports_tool_calling?: boolean;
  supports_thinking?: boolean;
  supports_fast?: boolean;
  speed_tier?: string;
  quality_tier?: string;
  cost_tier?: string;
  knowledge_level?: number;
  capability_tags?: string[];
  recommended_roles?: string[];
  notes?: string;
};

export type SidebarField = {
  id: string;
  label: string;
  type: "text" | "textarea" | "number" | "toggle" | "select" | "color" | "readonly" | "secret" | "api_keys" | "external_tokens" | "public_url" | "model_api_routes";
  default?: unknown;
  required?: boolean;
  help?: string;
  min?: number;
  max?: number;
  options?: SidebarFieldOption[];
  provider_id?: string;
  configured_field?: string;
  advanced?: boolean;
  api_keys?: Array<Record<string, unknown>>;
};

export type SidebarAction = {
  id: string;
  label: string;
  icon?: string;
  method?: "GET" | "POST" | "PUT" | "DELETE";
  endpoint?: string;
  payload?: Record<string, unknown>;
  preview_type?: "web" | "code" | "file" | "image";
  requires_approval?: boolean;
};

export type ComposerWidgetKind = "tool_toggle" | "button" | "panel" | "selector";

export type ComposerWidgetAction =
  | { type: "open_panel"; target_item_id?: string }
  | {
      type: "call_endpoint";
      endpoint: string;
      method?: "GET" | "POST" | "PUT" | "DELETE";
      payload?: Record<string, unknown>;
      result_surface?: "preview" | "chat" | "silent";
      requires_approval?: boolean;
    }
  | { type: "select_model"; profile_id?: string }
  | { type: "toggle_tool"; tool_id?: string };

export type ToolUiMetadata = {
  group_id?: string;
  group_label?: string;
  group_icon?: string;
  item_icon?: string;
  drop_capabilities?: string[];
  widget_kind?: ComposerWidgetKind | string | null;
  composer_label?: string;
  composer_description?: string;
  composer_icon?: string;
  composer_action?: ComposerWidgetAction;
};

export type ToolCapabilityRequirements = {
  requires_all?: string[];
  requires_any?: string[];
  forbids?: string[];
};

export type ToolSetupState = {
  status?: "ok" | "missing" | string;
  missing?: string[];
};

export type ToolInfo = {
  requires_approval?: boolean;
  approval_policy?: string;
  attachment_policy?: string;
  supports_attachments?: boolean | null;
  capability_requirements?: ToolCapabilityRequirements;
  requires_model_capabilities?: string[];
  requires_input_modalities?: string[];
  requires_runtime_capabilities?: string[];
  setup_state?: ToolSetupState;
  trusted?: boolean;
  source_pack_id?: string;
};

export type SidebarItem = {
  id: string;
  label: string;
  category: SidebarCategory;
  description?: string;
  badge?: string | null;
  tags?: string[];
  risk?: "low" | "medium" | "high" | string | null;
  ui?: ToolUiMetadata;
  tool_info?: ToolInfo;
  origin?: {
    kind: string;
    path?: string;
  };
  panel?: {
    kind: string;
    title?: string;
    fields?: SidebarField[];
    notes?: string[];
    models?: { id: string; name?: string }[];
    actions?: SidebarAction[];
  };
};

export type SettingsSection = {
  id: string;
  label: string;
  description?: string;
  fields: SidebarField[];
};

export type ComposerCommandCategory = "chat" | "model" | "mode" | "coding" | "tools" | "settings" | "debug";
export type ComposerCommandVisibility = "default" | "advanced" | "hidden";
export type ComposerCommandRisk = "low" | "medium" | "high";
export type ComposerCommandMode = "chat" | "coding" | "agent";

export type ComposerCommandArg = {
  name: string;
  type: "string" | "enum" | "boolean";
  required?: boolean;
  values?: string[];
};

export type ComposerCommandExecution =
  | { type: "frontend"; action: string }
  | { type: "model_command"; action: string }
  | { type: "settings_patch"; section: string; field: string }
  | { type: "rumi_function"; qualified_name: string }
  | { type: "chat_action"; action: string };

export type ComposerCommandItem = {
  id: string;
  name: string;
  aliases?: string[];
  label: string;
  description?: string;
  category: ComposerCommandCategory;
  visibility: ComposerCommandVisibility;
  modes?: ComposerCommandMode[];
  risk: ComposerCommandRisk;
  enabled?: boolean;
  active?: boolean;
  args?: ComposerCommandArg[];
  execution: ComposerCommandExecution;
};

export type ComposerCommandExecuteResult = {
  command: ComposerCommandItem;
  executed?: boolean;
  requires_approval?: boolean;
  action?: string;
  args?: Record<string, unknown>;
  result?: unknown;
  message?: string;
  candidates?: ModelCommandCandidate[];
  selected_model?: string | ModelCommandCandidate | null;
};

export type ShellRegion = {
  id: string;
  part_id?: string;
  renderer?: string;
  slot?: string;
  order?: number;
  enabled?: boolean;
};

export type ShellRenderer = {
  id: string;
  component: string;
  regions?: string[];
  fallback?: string;
  module?: string;
  export?: string;
  trust?: "local";
};

export type SkillCatalogItem = {
  id: string;
  label: string;
  description?: string;
  triggers?: string[];
  applies_to_tools?: string[];
  aliases?: string[];
  metadata?: Record<string, unknown>;
};

export type UICatalog = {
  app?: {
    id: string;
    name: string;
    icon?: string;
    account?: {
      display_name?: string;
      email?: string;
      plan_label?: string;
      avatar_url?: string;
      initial?: string;
      source?: string;
    };
  };
  agent_service?: {
    service_id?: string;
    version?: string;
    local_first?: boolean;
    core_requires_api_key?: boolean;
    default_profile?: string;
    counts?: Record<string, number>;
    capabilities?: Array<Record<string, unknown>>;
    profiles?: Array<Record<string, unknown>>;
    presets?: Array<Record<string, unknown>>;
    policy?: Record<string, unknown>;
  };
  shell?: {
    layout?: {
      id: string;
      regions?: ShellRegion[];
    };
    renderers?: ShellRenderer[];
  };
  parts?: Array<{
    id: string;
    kind: string;
    label?: string;
    uses?: string[];
    contracts?: Record<string, string>;
    schema?: Record<string, unknown>;
  }>;
  component_bindings?: Array<{
    part_id: string;
    component: string;
    requires?: string[];
    optional?: string[];
  }>;
  sidebar: {
    filters: { id: "all" | SidebarCategory; label: string }[];
    items: SidebarItem[];
  };
  settings: {
    sections: SettingsSection[];
    values: Record<string, Record<string, unknown>>;
  };
  chat_rendering: {
    renderers: Array<{
      id: string;
      block_types?: string[];
      widget_types?: string[];
      component: string;
      fallback?: string;
    }>;
  };
  skills?: SkillCatalogItem[];
  extension_points: Array<{
    id: string;
    path: string;
    description: string;
  }>;
  diagnostics?: Array<{
    level: "info" | "warning" | "error" | string;
    code: string;
    message: string;
    source: string;
  }>;
};

type ApiOk<T> = {
  status: "ok";
  data: T;
};

type ApiError = {
  status: "error";
  error: {
    code: string;
    message: string;
  };
};

type ApiEnvelope<T> = ApiOk<T> | ApiError;

type SendMessageOptions = {
  thinking_level?: string | null;
  tool_choice?: "auto" | "none" | "required" | Record<string, unknown>;
  parallel_tool_calls?: boolean;
  tool_policy?: Record<string, unknown>;
  attachments?: ChatAttachment[];
  tools?: string[];
  metadata?: Record<string, unknown>;
};

type ChatStreamError = string | { code?: string; message?: string };

export type ChatToolStreamEvent = ChatActivityEvent & {
  type:
    | "status"
    | "tool_call"
    | "tool_call_started"
    | "tool_call_delta"
    | "tool_call_completed"
    | "tool_result"
    | "browser_state_invalidated"
    | "browser_state_snapshot"
    | "browser_dom_snapshot"
    | "browser_screenshot"
    | "approval_requested"
    | "ai_retry_scheduled"
    | "task_failed";
};

export type ChatStreamEvent =
  | { type: "delta"; delta: string }
  | { type: "thinking_delta"; delta: string }
  | { type: "message" | "done" | "user_message"; message?: ChatMessage }
  | { type: "error"; error?: ChatStreamError }
  | ChatToolStreamEvent;

type ChatStreamHandlers = {
  onEvent?: (event: ChatStreamEvent) => void;
  onDelta?: (delta: string) => void;
  onThinkingDelta?: (delta: string) => void;
  onMessage?: (message: ChatMessage) => void;
  onUserMessage?: (message: ChatMessage) => void;
  signal?: AbortSignal;
};

function streamRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function streamString(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" ? value : "";
}

function streamMessageValue(record: Record<string, unknown>, data: Record<string, unknown>): ChatMessage | undefined {
  const value = record.message ?? data.message;
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as ChatMessage
    : undefined;
}

function streamErrorValue(record: Record<string, unknown>, data: Record<string, unknown>): ChatStreamError | undefined {
  const value = record.error ?? data.error;
  if (typeof value === "string") return value;
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as ChatStreamError;
  }
  const message = record.message ?? data.message;
  return typeof message === "string" && message.trim() ? { message } : undefined;
}

export function normalizeChatStreamEvent(value: unknown): ChatStreamEvent | null {
  const record = streamRecord(value);
  const rawType = streamString(record, "type").trim();
  if (!rawType) return null;
  const data = streamRecord(record.data);
  const delta = streamString(data, "delta") || streamString(record, "delta") || streamString(data, "content") || streamString(record, "content");

  if (rawType === "delta" || rawType === "content_delta") {
    return { type: "delta", delta };
  }
  if (rawType === "thinking_delta") {
    return { type: "thinking_delta", delta };
  }
  if (rawType === "user_message" || rawType === "user_message_committed") {
    return { type: "user_message", message: streamMessageValue(record, data) };
  }
  if (rawType === "message" || rawType === "assistant_message_completed") {
    return { type: "message", message: streamMessageValue(record, data) };
  }
  if (rawType === "done" || rawType === "stream_end") {
    return { type: "done", message: streamMessageValue(record, data) };
  }
  if (rawType === "error" || rawType === "cancelled") {
    return { type: "error", error: rawType === "cancelled" ? "cancelled" : streamErrorValue(record, data) };
  }

  const merged: Record<string, unknown> = { ...record, ...data, type: rawType };
  delete merged.data;
  delete merged.schema_version;
  return merged as ChatStreamEvent;
}

const BROWSER_COMPUTER_APPROVAL_TOOLS = new Set([
  "browser_computer",
  "browser_companion",
  "browser_use",
  "computer_use",
  "browser_open_url",
  "open_browser",
]);

const BROWSER_OPEN_ACTION_ALIASES = new Set([
  "browser_open_url",
  "open_browser",
  "open_url",
]);

const COMPUTER_APPROVAL_ACTION_ALIASES = new Set([
  "context",
  "app_context",
  "state",
  "apps",
  "list_apps",
  "open_apps",
  "applications",
  "windows",
  "list_windows",
  "select_app",
  "show_app",
  "focus_app",
  "activate_app",
  "select_window",
  "screenshot",
  "move",
  "click",
  "drag",
  "type",
  "key",
  "scroll",
  "observe",
  "semantic_action",
  "press",
  "pid_event",
]);

export function usesBrowserComputerApprovalEndpoint(toolName: string): boolean {
  return BROWSER_COMPUTER_APPROVAL_TOOLS.has(String(toolName || "").trim());
}

export function normalizeBrowserComputerApprovalAction(toolName: string, action: string): string {
  const normalizedAction = String(action || "").trim();
  if (usesBrowserComputerApprovalEndpoint(toolName) && BROWSER_OPEN_ACTION_ALIASES.has(normalizedAction)) {
    return "browser.open_url";
  }
  if (
    usesBrowserComputerApprovalEndpoint(toolName)
    && normalizedAction
    && !normalizedAction.includes(".")
    && COMPUTER_APPROVAL_ACTION_ALIASES.has(normalizedAction)
  ) {
    return `computer.${normalizedAction}`;
  }
  return normalizedAction;
}

function isUnsafeHttpMethod(method: string): boolean {
  return !["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase());
}

function sessionStorageOrNull(): Storage | null {
  try {
    return typeof sessionStorage === "undefined" ? null : sessionStorage;
  } catch {
    return null;
  }
}

function generateCsrfToken(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `csrf-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function getDefaultspackCsrfToken(): string {
  const storage = sessionStorageOrNull();
  const stored = storage?.getItem(DEFAULTSPACK_CSRF_STORAGE_KEY);
  if (stored) return stored;
  const token = generateCsrfToken();
  try {
    storage?.setItem(DEFAULTSPACK_CSRF_STORAGE_KEY, token);
  } catch {
    // A nonempty per-request token still satisfies the local CSRF guard.
  }
  return token;
}

export function defaultspackApiHeaders(method: string, headers?: HeadersInit): Headers {
  const nextHeaders = new Headers(headers);
  if (!nextHeaders.has("Content-Type")) {
    nextHeaders.set("Content-Type", "application/json");
  }
  const csrfHeader = nextHeaders.get("X-Rumi-CSRF");
  if (isUnsafeHttpMethod(method) && (!csrfHeader || !csrfHeader.trim())) {
    nextHeaders.set("X-Rumi-CSRF", getDefaultspackCsrfToken());
  }
  return nextHeaders;
}

export function defaultspackApiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const method = (init.method ?? "GET").toUpperCase();
  return fetch(input, {
    ...init,
    method,
    headers: defaultspackApiHeaders(method, init.headers),
  });
}

function truncateApiErrorDetail(value: string, limit = 700): string {
  const text = value.trim().replace(/\s+/g, " ");
  if (text.length <= limit) return text;
  return `${text.slice(0, limit).trim()}...`;
}

function defaultspackApiStatusHint(status: number): string {
  if (status === 400) return "リクエスト形式、モデル設定、添付ファイル、または選択中の tool が backend と噛み合っていません。";
  if (status === 401) return "認証が必要です。ログイン状態、APIキー、OAuth 接続を確認してください。";
  if (status === 403) return "権限または承認で拒否されました。承認カード、CSRF、APIキーの利用権限、モデルアクセス権を確認してください。";
  if (status === 404) return "対象の会話、モデル、ファイル、または endpoint が見つかりません。";
  if (status === 409) return "同時実行や状態の衝突が起きています。画面を更新して再試行してください。";
  if (status === 429) return "レート制限またはクォータ上限です。少し待つか、別のキー/モデルに切り替えてください。";
  if (status >= 500) return "backend または provider 側の障害です。少し待って再試行してください。";
  return "backend からエラーが返りました。詳細を確認して再試行してください。";
}

export function explainDefaultspackApiError(
  status: number,
  error?: { code?: string; message?: string },
  statusText?: string,
): string {
  const label = status ? `HTTP ${status}${statusText ? ` ${statusText}` : ""}` : "defaultspack API error";
  const code = error?.code ? ` (${error.code})` : "";
  const detail = error?.message ? truncateApiErrorDetail(error.message) : "";
  return [
    `${label}${code}`,
    defaultspackApiStatusHint(status),
    detail ? `詳細: ${detail}` : "",
  ].filter(Boolean).join("\n");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await defaultspackApiFetch(path, {
    ...init,
  });

  let payload: ApiEnvelope<T>;
  try {
    payload = (await response.json()) as ApiEnvelope<T>;
  } catch {
    if (!response.ok) {
      throw new Error(explainDefaultspackApiError(response.status, undefined, response.statusText));
    }
    throw new Error("defaultspack API returned an invalid JSON response");
  }

  if (!response.ok || payload.status === "error") {
    throw new Error(explainDefaultspackApiError(
      response.status,
      payload.status === "error" ? payload.error : undefined,
      response.statusText,
    ));
  }

  return payload.data;
}

function encodeQueryValue(value: unknown): string | null {
  if (value === undefined || value === null || value === "") return null;
  if (Array.isArray(value)) {
    const items = value.map((item) => String(item).trim()).filter(Boolean);
    return items.length ? items.join(",") : null;
  }
  return String(value);
}

function withQuery(path: string, params?: Record<string, unknown>): string {
  if (!params) return path;
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    const encoded = encodeQueryValue(value);
    if (encoded !== null) query.set(key, encoded);
  }
  const suffix = query.toString();
  return suffix ? `${path}?${suffix}` : path;
}

export function arrayFromRecord<T>(value: Record<string, T> | T[] | undefined | null): T[] {
  if (Array.isArray(value)) return value;
  if (value && typeof value === "object") return Object.values(value);
  return [];
}

function messageRequestBody(
  text: string,
  options?: SendMessageOptions,
): Record<string, unknown> {
  return {
    message: {
      role: "user",
      content: text,
      attachments: options?.attachments?.length ? options.attachments : undefined,
      metadata: options?.metadata,
    },
    tools: Array.isArray(options?.tools) ? options.tools : undefined,
    params: {
      thinking_level: options?.thinking_level ?? undefined,
      tool_choice: options?.tool_choice ?? undefined,
      parallel_tool_calls: options?.parallel_tool_calls ?? undefined,
      tool_policy: options?.tool_policy ?? undefined,
    },
  };
}

async function readStreamEvents(
  response: Response,
  handlers: ChatStreamHandlers = {},
): Promise<ChatMessage | null> {
  if (!response.body) {
    throw new Error("defaultspack API returned an empty stream");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalMessage: ChatMessage | null = null;

  const streamErrorMessage = (value: ChatStreamError | undefined): string => {
    if (typeof value === "string" && value.trim()) return value;
    if (value && typeof value === "object" && typeof value.message === "string") {
      return value.message;
    }
    return "defaultspack stream failed";
  };

  const consumePacket = (packet: string) => {
    const dataLines = packet
      .split(/\r?\n/)
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart());
    if (!dataLines.length) return;
    const raw = dataLines.join("\n");
    if (!raw || raw === "[DONE]") return;
    let event: ChatStreamEvent;
    try {
      const parsed = JSON.parse(raw) as unknown;
      const normalized = normalizeChatStreamEvent(parsed);
      if (!normalized) {
        throw new Error("empty event");
      }
      event = normalized;
    } catch {
      throw new Error("defaultspack stream returned a malformed event");
    }
    handlers.onEvent?.(event);
    if (event.type === "delta") {
      handlers.onDelta?.(event.delta);
    } else if (event.type === "thinking_delta") {
      handlers.onThinkingDelta?.(event.delta);
    } else if (event.type === "user_message" && event.message) {
      handlers.onUserMessage?.(event.message);
    } else if ((event.type === "message" || event.type === "done") && event.message) {
      finalMessage = event.message;
      handlers.onMessage?.(event.message);
    } else if (event.type === "error") {
      throw new Error(streamErrorMessage(event.error));
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    const packets = buffer.split(/\r?\n\r?\n/);
    buffer = packets.pop() ?? "";
    for (const packet of packets) {
      consumePacket(packet);
    }
    if (done) break;
  }
  if (buffer.trim()) {
    consumePacket(buffer);
  }
  if (!finalMessage) {
    throw new Error("defaultspack stream ended before a final response arrived");
  }
  return finalMessage;
}

export const api = {
  listConversations(options?: ConversationListOptions) {
    return request<{ conversations: Conversation[]; total: number }>(
      withQuery("/api/chat/conversations", options),
    );
  },

  searchConversations(query: string, options?: ConversationSearchOptions) {
    return request<{ results: ConversationSearchResult[]; total: number; query: string }>("/api/chat/search", {
      method: "POST",
      body: JSON.stringify({
        query,
        mode: "conversations",
        date_filter: options?.date_filter ?? "all",
        is_starred: options?.is_starred,
        is_archived: options?.is_archived,
        role: options?.role ?? "all",
        limit: options?.limit ?? 12,
        offset: options?.offset ?? 0,
      }),
    });
  },

  getConversation(id: string) {
    return request<Conversation>(`/api/chat/conversations/${id}`);
  },

  createConversation(options?: {
    model?: string;
    system_prompt_id?: string | null;
    agent_id?: string | null;
    tags?: string[];
    parent_conversation_id?: string | null;
    conversation_kind?: string | null;
    group_id?: string | null;
    metadata?: Record<string, unknown>;
  }) {
    return request<Conversation>("/api/chat/conversations", {
      method: "POST",
      body: JSON.stringify(options ?? {}),
    });
  },

  updateConversation(id: string, updates: Partial<Conversation>) {
    return request<Conversation>(`/api/chat/conversations/${id}`, {
      method: "PUT",
      body: JSON.stringify({ updates }),
    });
  },

  deleteConversation(id: string) {
    return request<{ deleted: boolean }>(`/api/chat/conversations/${id}`, {
      method: "DELETE",
    });
  },

  sendMessage(
    conversationId: string,
    text: string,
    options?: SendMessageOptions,
  ) {
    return request<ChatMessage>(
      `/api/chat/conversations/${conversationId}/messages`,
      {
        method: "POST",
        body: JSON.stringify(messageRequestBody(text, options)),
      },
    );
  },

  async streamMessage(
    conversationId: string,
    text: string,
    options?: SendMessageOptions,
    handlers?: ChatStreamHandlers,
  ) {
    const response = await defaultspackApiFetch(`/api/chat/conversations/${conversationId}/stream`, {
      method: "POST",
      body: JSON.stringify(messageRequestBody(text, options)),
      signal: handlers?.signal,
    });

    const contentType = response.headers.get("Content-Type") ?? "";
    if (!response.ok || !contentType.includes("text/event-stream")) {
      let payload: ApiEnvelope<ChatMessage>;
      try {
        payload = (await response.json()) as ApiEnvelope<ChatMessage>;
      } catch {
        throw new Error(explainDefaultspackApiError(response.status, undefined, response.statusText));
      }
      if (payload.status === "error") {
        throw new Error(explainDefaultspackApiError(response.status, payload.error, response.statusText));
      }
      if (!response.ok) {
        throw new Error(explainDefaultspackApiError(response.status, undefined, response.statusText));
      }
      handlers?.onMessage?.(payload.data);
      return payload.data;
    }
    return readStreamEvents(response, handlers);
  },

  stopMessage(conversationId: string) {
    return request<{ success: boolean; conversation_id: string; cancelled: boolean }>(
      `/api/chat/conversations/${conversationId}/stop`,
      {
        method: "POST",
        body: JSON.stringify({}),
      },
    );
  },

  listModelProfiles() {
    return request<{ profiles: ModelProfile[]; count: number }>("/api/ai/profiles", {
      cache: "no-store",
    });
  },

  searchModels(filters: Record<string, unknown>) {
    return request<ModelSearchResponse>("/api/ai/models/search", {
      method: "POST",
      body: JSON.stringify(filters),
    });
  },

  conversationSteer(payload: Record<string, unknown>) {
    return request<ConversationSteerResponse>("/api/chat/steer", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  listSystemPrompts() {
    return request<SystemPromptListResponse>("/api/system-prompts", {
      cache: "no-store",
    });
  },

  createSystemPrompt(payload: Partial<SystemPromptRecord> & { activate?: boolean }) {
    return request<SystemPromptListResponse>("/api/system-prompts", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  updateSystemPrompt(promptId: string, updates: Partial<SystemPromptRecord>) {
    return request<SystemPromptListResponse>(`/api/system-prompts/${encodeURIComponent(promptId)}`, {
      method: "PUT",
      body: JSON.stringify(updates),
    });
  },

  deleteSystemPrompt(promptId: string) {
    return request<SystemPromptListResponse>(`/api/system-prompts/${encodeURIComponent(promptId)}`, {
      method: "DELETE",
    });
  },

  activateSystemPrompt(promptId: string) {
    return request<SystemPromptListResponse>(`/api/system-prompts/${encodeURIComponent(promptId)}/activate`, {
      method: "POST",
      body: JSON.stringify({}),
    });
  },

  health() {
    return request<{ status: string; pack: string; ts: string }>("/api/health");
  },

  uiCatalog() {
    return request<UICatalog>("/api/ui/catalog");
  },

  uiSettings() {
    return request<{ sections: SettingsSection[]; values: Record<string, Record<string, unknown>> }>(
      "/api/ui/settings",
      { cache: "no-store" },
    );
  },

  uiCommands() {
    return request<{ commands: ComposerCommandItem[] }>("/api/ui/commands");
  },

  executeUiCommand(payload: {
    command: string;
    args?: Record<string, unknown>;
    conversation_id?: string | null;
    mode?: ComposerCommandMode;
  }) {
    return request<ComposerCommandExecuteResult>("/api/ui/commands/execute", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  updateUiSettings(values: Record<string, Record<string, unknown>>) {
    return request<{ values: Record<string, Record<string, unknown>> }>("/api/ui/settings", {
      method: "PUT",
      body: JSON.stringify({ values }),
    });
  },

  writeClipboard(content: string) {
    return request<{ written: boolean }>("/api/ui/clipboard", {
      method: "POST",
      body: JSON.stringify({ content }),
    });
  },

  saveProviderApiKey(providerId: string, value: string, options?: {
    apiId?: string;
    name?: string;
    baseUrl?: string;
    allowedModels?: string[];
    defaultModel?: string;
    notes?: string;
    quotaLabel?: string;
    kind?: string;
  }) {
    return request<{ provider_id: string; api_id?: string; name?: string; configured: boolean; kind?: string; model_availability?: ModelAvailabilityAfterKeySave }>("/api/ai/provider-key", {
      method: "POST",
      body: JSON.stringify({
        provider_id: providerId,
        value,
        api_id: options?.apiId,
        name: options?.name,
        base_url: options?.baseUrl,
        allowed_models: options?.allowedModels,
        default_model: options?.defaultModel,
        notes: options?.notes,
        quota_label: options?.quotaLabel,
        kind: options?.kind,
      }),
    });
  },

  registerCustomProvider(providerId: string, options?: { label?: string; kind?: string }) {
    return request<{ provider_id: string; label?: string; kind?: string; builtin?: boolean }>("/api/ai/provider-key", {
      method: "POST",
      body: JSON.stringify({
        action: "register_provider",
        provider_id: providerId,
        label: options?.label,
        kind: options?.kind,
      }),
    });
  },

  deleteCustomProvider(providerId: string) {
    return request<{ provider_id: string; deleted?: boolean }>("/api/ai/provider-key", {
      method: "POST",
      body: JSON.stringify({
        action: "delete_provider",
        provider_id: providerId,
      }),
    });
  },

  renameProviderApiKey(providerId: string, apiId: string, name: string) {
    return request<{ provider_id: string; api_id?: string; name?: string; configured: boolean }>("/api/ai/provider-key", {
      method: "POST",
      body: JSON.stringify({
        action: "rename",
        provider_id: providerId,
        api_id: apiId,
        name,
        new_api_id: name,
      }),
    });
  },

  deleteProviderApiKey(providerId: string, apiId: string) {
    return request<{ provider_id: string; api_id?: string; configured: boolean; cleared?: boolean }>("/api/ai/provider-key", {
      method: "POST",
      body: JSON.stringify({
        action: "delete",
        provider_id: providerId,
        api_id: apiId,
      }),
    });
  },

  providerOAuthStatus(providerId?: string) {
    const suffix = providerId ? `?provider_id=${encodeURIComponent(providerId)}` : "";
    return request<{ provider?: Record<string, unknown>; providers?: Record<string, Record<string, unknown>> }>(`/api/ai/oauth${suffix}`, { cache: "no-store" });
  },

  saveProviderOAuthClientConfig(providerId: string, clientConfig: string) {
    return request<{ provider_id: string; client_configured: boolean; client_label?: string }>("/api/ai/oauth", {
      method: "POST",
      body: JSON.stringify({
        action: "save_client",
        provider_id: providerId,
        client_config: clientConfig,
      }),
    });
  },

  startProviderOAuth(providerId: string) {
    return request<{ provider_id: string; authorize_url: string; redirect_uri: string; scopes: string[] }>("/api/ai/oauth", {
      method: "POST",
      body: JSON.stringify({
        action: "start",
        provider_id: providerId,
      }),
    });
  },

  disconnectProviderOAuth(providerId: string) {
    return request<{ provider_id: string; connected: boolean }>("/api/ai/oauth", {
      method: "POST",
      body: JSON.stringify({
        action: "disconnect",
        provider_id: providerId,
      }),
    });
  },

  clearProviderOAuthClientConfig(providerId: string) {
    return request<{ provider_id: string; client_configured: boolean; connected: boolean }>("/api/ai/oauth", {
      method: "POST",
      body: JSON.stringify({
        action: "clear_client",
        provider_id: providerId,
      }),
    });
  },

  saveExternalToken(providerId: string, value: string, options?: { tokenId?: string; name?: string; kind?: string }) {
    return request<{ provider_id: string; token_id?: string; name?: string; kind?: string; configured: boolean }>("/api/external/tokens", {
      method: "POST",
      body: JSON.stringify({
        provider_id: providerId,
        token_id: options?.tokenId,
        name: options?.name,
        kind: options?.kind,
        value,
      }),
    });
  },

  renameExternalToken(providerId: string, tokenId: string, name: string) {
    return request<{ provider_id: string; token_id?: string; name?: string; configured: boolean }>("/api/external/tokens", {
      method: "POST",
      body: JSON.stringify({
        action: "rename",
        provider_id: providerId,
        token_id: tokenId,
        name,
        new_token_id: name,
      }),
    });
  },

  deleteExternalToken(providerId: string, tokenId: string) {
    return request<{ provider_id: string; token_id?: string; configured: boolean; cleared?: boolean }>("/api/external/tokens", {
      method: "POST",
      body: JSON.stringify({
        action: "delete",
        provider_id: providerId,
        token_id: tokenId,
      }),
    });
  },

  listPublicUrlProviders() {
    return request<{ providers: Array<Record<string, unknown>>; default_local_url?: string }>("/api/webhooks/public-urls");
  },

  createPublicUrl(payload: { provider_id?: string; provider?: string; local_url?: string; route_path?: string; ttl_seconds?: number }) {
    return request<Record<string, unknown>>("/api/webhooks/public-urls", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  closePublicUrl(urlId: string) {
    return request<Record<string, unknown>>(`/api/webhooks/public-urls/${encodeURIComponent(urlId)}`, {
      method: "DELETE",
    });
  },

  conversationPreview(conversationId: string) {
    return request<{ conversation_id: string; previews: ToolPreviewItem[]; summary: Record<string, number> }>(
      `/api/ui/conversations/${conversationId}/preview`,
    );
  },

  exportConversation(conversationId: string, format = "markdown") {
    return request<{ content: string; format?: string }>(
      `/api/chat/conversations/${conversationId}/export`,
      {
        method: "POST",
        body: JSON.stringify({ format }),
      },
    );
  },

  listArtifacts() {
    return request<Record<string, unknown>>("/api/artifacts");
  },

  webSearch(query: string, allowNetwork = false) {
    return request<Record<string, unknown>>("/api/research/web-search", {
      method: "POST",
      body: JSON.stringify({ query, allow_network: allowNetwork, limit: 5 }),
    });
  },

  redditSearch(query: string, allowNetwork = false) {
    return request<Record<string, unknown>>("/api/research/reddit-search", {
      method: "POST",
      body: JSON.stringify({ query, allow_network: allowNetwork, limit: 5 }),
    });
  },

  browserComputer(action: string, payload?: Record<string, unknown>) {
    return request<Record<string, unknown>>("/api/tools/browser-computer", {
      method: "POST",
      body: JSON.stringify({ action, payload: payload ?? {} }),
    });
  },

  approveBrowserComputerAction(toolName: string, action: string, payload?: Record<string, unknown>) {
    const normalizedAction = normalizeBrowserComputerApprovalAction(toolName, action);
    if (usesBrowserComputerApprovalEndpoint(toolName)) {
      return request<Record<string, unknown>>("/api/tools/browser-computer", {
        method: "POST",
        body: JSON.stringify({ action: normalizedAction, payload: payload ?? {} }),
      });
    }
    return request<Record<string, unknown>>("/api/tools/invoke", {
      method: "POST",
      body: JSON.stringify({
        tool_name: toolName,
        arguments: { ...(payload ?? {}), action: normalizedAction },
      }),
    });
  },

  invokeTool(toolName: string, argumentsPayload?: Record<string, unknown>, context?: Record<string, unknown>) {
    return request<Record<string, unknown>>("/api/tools/invoke", {
      method: "POST",
      body: JSON.stringify({
        tool_name: toolName,
        arguments: argumentsPayload ?? {},
        ...(context ? { context } : {}),
      }),
    });
  },

  getBrowserScreenshots(conversationId: string, runId: string) {
    return request<{ screenshots: BrowserScreenshot[]; omitted_count?: number }>(
      `/api/chat/conversations/${conversationId}/run-results/${runId}/browser-screenshots`,
    );
  },

  listSchedules() {
    return request<Record<string, unknown>>("/api/agent/schedules");
  },

  createSchedule(payload: Record<string, unknown>) {
    return request<Record<string, unknown>>("/api/agent/schedules", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  updateSchedule(scheduleId: string, payload: Record<string, unknown>) {
    return request<Record<string, unknown>>(`/api/agent/schedules/${encodeURIComponent(scheduleId)}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },

  deleteSchedule(scheduleId: string) {
    return request<Record<string, unknown>>(`/api/agent/schedules/${encodeURIComponent(scheduleId)}`, {
      method: "DELETE",
    });
  },

  getScheduleHistory(scheduleId: string) {
    return request<Record<string, unknown>>(`/api/agent/schedules/${encodeURIComponent(scheduleId)}/history`, {
      cache: "no-store",
    });
  },

  getOperationsCompanyStatus() {
    return request<OperationsCompanyStatus>("/api/agent/company/status");
  },

  bootstrapOperationsCompany(options?: {
    start_nonstop?: boolean;
    heartbeat_minutes?: number;
    model?: string;
  }) {
    return request<OperationsCompanyStatus>("/api/agent/company/bootstrap", {
      method: "POST",
      body: JSON.stringify(options ?? {}),
    });
  },

  getMimoCodingCompanyStatus() {
    return request<MimoCodingCompanyStatus>("/api/agent/mimo-company/status");
  },

  bootstrapMimoCodingCompany(options?: {
    start_nonstop?: boolean;
    heartbeat_minutes?: number;
    review_interval_minutes?: number;
    qa_interval_minutes?: number;
    model?: string;
    vision_model?: string;
    fast_model?: string;
    qa_targets?: string[];
    docker_worker_count?: number;
    docker_personas?: string[];
    run_initial_review_now?: boolean;
    seed_tasks?: boolean;
    seed_knowledge?: boolean;
  }) {
    return request<MimoCodingCompanyStatus>("/api/agent/mimo-company/bootstrap", {
      method: "POST",
      body: JSON.stringify(options ?? {}),
    });
  },

  listCompanies(options?: { limit?: number; offset?: number }) {
    return request<{ companies: CompanyRecord[]; total: number }>(
      withQuery("/api/company", options),
      { cache: "no-store" },
    );
  },

  getCompany(companyId: string) {
    return request<CompanyRecord>(`/api/company/${encodeURIComponent(companyId)}`, { cache: "no-store" });
  },

  createCompany(payload: {
    id?: string;
    company_id?: string;
    name: string;
    description?: string;
    settings?: Record<string, unknown>;
    metadata?: Record<string, unknown>;
  }) {
    return request<CompanyRecord>("/api/company", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  updateCompany(companyId: string, updates: Partial<CompanyRecord>) {
    return request<CompanyRecord>(`/api/company/${encodeURIComponent(companyId)}`, {
      method: "PUT",
      body: JSON.stringify({ company_id: companyId, updates }),
    });
  },

  deleteCompany(companyId: string) {
    return request<{ deleted: boolean; company_id: string }>(`/api/company/${encodeURIComponent(companyId)}`, {
      method: "DELETE",
    });
  },

  getCompanyStatus(options?: string | { companyId?: string | null; conversationId?: string | null; bootstrap?: boolean }) {
    const query = typeof options === "string"
      ? { company_id: options }
      : {
          company_id: options?.companyId,
          conversation_id: options?.conversationId,
          bootstrap: options?.bootstrap,
        };
    return request<CompanyStatusResponse>(
      withQuery("/api/company/status", query),
      { cache: "no-store" },
    );
  },

  bootstrapCompanyWorkspace(metadata?: Record<string, unknown>, options?: { conversationId?: string | null; scope?: "conversation" | "default" }) {
    return request<{ bootstrapped: boolean; company: CompanyRecord }>("/api/company/bootstrap", {
      method: "POST",
      body: JSON.stringify({
        ...(metadata ? { metadata } : {}),
        ...(options?.conversationId ? { conversation_id: options.conversationId } : {}),
        ...(options?.scope ? { scope: options.scope } : {}),
      }),
    });
  },

  getCompanySettings(companyId: string) {
    return request<{ settings: Record<string, unknown> }>(
      withQuery(`/api/company/${encodeURIComponent(companyId)}/settings`, { company_id: companyId }),
      { cache: "no-store" },
    );
  },

  updateCompanySettings(companyId: string, settings: Record<string, unknown>, replace = false) {
    return request<{ settings: Record<string, unknown> }>(`/api/company/${encodeURIComponent(companyId)}/settings`, {
      method: "POST",
      body: JSON.stringify({ company_id: companyId, action: "update", settings, replace }),
    });
  },

  listCompanyAgents(companyId: string) {
    return request<{ agents: CompanyAgent[]; total: number }>(
      withQuery(`/api/company/${encodeURIComponent(companyId)}/agents`, { company_id: companyId }),
      { cache: "no-store" },
    );
  },

  upsertCompanyAgent(companyId: string, agent: Partial<CompanyAgent>) {
    return request<CompanyAgent>(`/api/company/${encodeURIComponent(companyId)}/agents`, {
      method: "POST",
      body: JSON.stringify({ company_id: companyId, action: "upsert", agent }),
    });
  },

  listCompanyChannels(companyId: string) {
    return request<{ channels: CompanyChannel[]; total: number }>(
      withQuery(`/api/company/${encodeURIComponent(companyId)}/channels`, { company_id: companyId }),
      { cache: "no-store" },
    );
  },

  upsertCompanyChannel(companyId: string, channel: Partial<CompanyChannel>) {
    return request<CompanyChannel>(`/api/company/${encodeURIComponent(companyId)}/channels`, {
      method: "POST",
      body: JSON.stringify({ company_id: companyId, action: "upsert", channel }),
    });
  },

  listCompanyMessages(companyId: string, options?: { channel_id?: string; limit?: number; offset?: number }) {
    return request<{ messages: CompanyMessage[]; total: number }>(
      withQuery(`/api/company/${encodeURIComponent(companyId)}/messages`, { company_id: companyId, ...options }),
      { cache: "no-store" },
    );
  },

  sendCompanyMessage(companyId: string, payload: {
    content: string;
    channel_id?: string;
    sender_id?: string;
    mentions?: string[];
    task_ids?: string[];
    metadata?: Record<string, unknown>;
  }) {
    return request<CompanyMessage>(`/api/company/${encodeURIComponent(companyId)}/messages`, {
      method: "POST",
      body: JSON.stringify({ company_id: companyId, action: "create", ...payload }),
    });
  },

  listCompanyTasks(companyId: string, options?: { status?: string; target_agent_id?: string; limit?: number; offset?: number }) {
    return request<{ tasks: CompanyTask[]; total: number }>(
      withQuery(`/api/company/${encodeURIComponent(companyId)}/tasks`, { company_id: companyId, ...options }),
      { cache: "no-store" },
    );
  },

  createCompanyTask(companyId: string, payload: {
    title: string;
    description?: string;
    target_agent_ids?: string[];
    source?: string;
    metadata?: Record<string, unknown>;
  }) {
    return request<CompanyTask>(`/api/company/${encodeURIComponent(companyId)}/tasks`, {
      method: "POST",
      body: JSON.stringify({ company_id: companyId, action: "create", ...payload }),
    });
  },

  updateCompanyTask(companyId: string, taskId: string, updates: Partial<CompanyTask>) {
    return request<CompanyTask>(`/api/company/${encodeURIComponent(companyId)}/tasks`, {
      method: "POST",
      body: JSON.stringify({ company_id: companyId, action: "update", task_id: taskId, updates }),
    });
  },

  dispatchCompanyTask(companyId: string, taskId: string, policy?: Record<string, unknown>) {
    return request<Record<string, unknown>>(`/api/company/${encodeURIComponent(companyId)}/dispatch`, {
      method: "POST",
      body: JSON.stringify({ company_id: companyId, task_id: taskId, policy }),
    });
  },

  listCompanyRuns(companyId: string, options?: { agent_id?: string; task_id?: string; status?: string; limit?: number }) {
    return request<{ runs: CompanyRunLink[]; total: number }>(
      withQuery(`/api/company/${encodeURIComponent(companyId)}/runs`, { company_id: companyId, ...options }),
      { cache: "no-store" },
    );
  },

  listCompanyAgentInbox(companyId: string, agentId: string, options?: { status?: string; kind?: string; limit?: number }) {
    return request<{ inbox: CompanyInboxItem[]; total: number }>(
      withQuery(`/api/company/${encodeURIComponent(companyId)}/agents/${encodeURIComponent(agentId)}/inbox`, {
        company_id: companyId,
        agent_id: agentId,
        ...options,
      }),
      { cache: "no-store" },
    );
  },

  listCompanyInboundRoutes(companyId: string) {
    return request<{ routes: CompanyInboundRoute[]; total: number }>(
      withQuery(`/api/company/${encodeURIComponent(companyId)}/inbound-routes`, { company_id: companyId }),
      { cache: "no-store" },
    );
  },

  upsertCompanyInboundRoute(companyId: string, route: Partial<CompanyInboundRoute>) {
    return request<CompanyInboundRoute>(`/api/company/${encodeURIComponent(companyId)}/inbound-routes`, {
      method: "POST",
      body: JSON.stringify({ company_id: companyId, action: "upsert", route }),
    });
  },

  deleteCompanyInboundRoute(companyId: string, routeId: string) {
    return request<{ deleted: boolean; route_id: string }>(`/api/company/${encodeURIComponent(companyId)}/inbound-routes`, {
      method: "POST",
      body: JSON.stringify({ company_id: companyId, action: "delete", route_id: routeId }),
    });
  },

  triggerSchedule(scheduleId: string) {
    return request<Record<string, unknown>>(`/api/agent/schedules/${scheduleId}/trigger`, {
      method: "POST",
      body: JSON.stringify({}),
    });
  },

  pauseSchedule(scheduleId: string) {
    return request<Record<string, unknown>>(`/api/agent/schedules/${encodeURIComponent(scheduleId)}/pause`, {
      method: "POST",
      body: JSON.stringify({}),
    });
  },

  resumeSchedule(scheduleId: string) {
    return request<Record<string, unknown>>(`/api/agent/schedules/${encodeURIComponent(scheduleId)}/resume`, {
      method: "POST",
      body: JSON.stringify({}),
    });
  },

  listChannels() {
    return request<Record<string, unknown>>("/api/chat/channels");
  },

  getP2PStatus() {
    return request<P2PStatusResponse>("/api/p2p/status", { cache: "no-store" });
  },

  getP2PIdentity(label?: string) {
    return request<{ identity: P2PIdentity; p2p: P2PSettings }>(
      withQuery("/api/p2p/identity", { label }),
      { cache: "no-store" },
    );
  },

  listP2PPeers() {
    return request<{ peers: P2PPeer[] }>("/api/p2p/peers", { cache: "no-store" });
  },

  approveP2PPeer(payload: {
    peer_id: string;
    fingerprint?: string;
    hmac_secret?: string;
    shared_secret?: string;
    capabilities?: string[];
    allowed_company_ids?: string[];
    label?: string;
    metadata?: Record<string, unknown>;
  }) {
    return request<{ peer: P2PPeer }>("/api/p2p/peers", {
      method: "POST",
      body: JSON.stringify({ action: "approve", ...payload }),
    });
  },

  blockP2PPeer(peerId: string, reason?: string) {
    return request<{ peer: P2PPeer }>("/api/p2p/peers", {
      method: "POST",
      body: JSON.stringify({ action: "block", peer_id: peerId, reason }),
    });
  },

  startP2PPairing(payload?: {
    peer_id?: string;
    peer_fingerprint?: string;
    peer_label?: string;
    ttl_seconds?: number;
    capabilities?: string[];
    allowed_company_ids?: string[];
  }) {
    return request<{ pairing: P2PPairing }>("/api/p2p/pairing/start", {
      method: "POST",
      body: JSON.stringify(payload ?? {}),
    });
  },

  acceptP2PPairing(payload: {
    code: string;
    peer_id?: string;
    peer_fingerprint?: string;
    peer_label?: string;
    hmac_secret?: string;
    shared_secret?: string;
    capabilities?: string[];
    allowed_company_ids?: string[];
  }) {
    return request<{ ok: boolean; pairing: P2PPairing; peer?: P2PPeer; hmac_secret?: string }>("/api/p2p/pairing/accept", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  rejectP2PPairing(code: string, reason?: string) {
    return request<{ ok: boolean; pairing: P2PPairing }>("/api/p2p/pairing/reject", {
      method: "POST",
      body: JSON.stringify({ code, reason }),
    });
  },

  sendP2PMessage(peerId: string, payload: {
    text?: string;
    message?: string;
    body?: Record<string, unknown>;
    type?: string;
    metadata?: Record<string, unknown>;
    ttl_seconds?: number;
  }) {
    return request<{ envelope: Record<string, unknown>; peer: P2PPeer }>("/api/p2p/messages/send", {
      method: "POST",
      body: JSON.stringify({ peer_id: peerId, ...payload }),
    });
  },

  createShare(payload: Record<string, unknown>) {
    return request<Record<string, unknown>>("/api/share", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  compactConversation(conversationId: string, options?: CompactConversationOptions) {
    return request<CompactConversationResult>(
      `/api/chat/conversations/${encodeURIComponent(conversationId)}/compact`,
      {
        method: "POST",
        body: JSON.stringify({ conversation_id: conversationId, ...(options ?? {}) }),
      },
    );
  },

  autoCompactConversation(conversationId: string, options?: CompactConversationOptions & { mode?: "suggest" | "apply" }) {
    return request<CompactConversationResult>(
      `/api/chat/conversations/${encodeURIComponent(conversationId)}/auto-compact`,
      {
        method: "POST",
        body: JSON.stringify({ conversation_id: conversationId, mode: options?.mode ?? "suggest", ...(options ?? {}) }),
      },
    );
  },

  getCodingContext(options?: { directory?: string; workspace_id?: string | null }) {
    return request<CodingContextResponse>(
      withQuery("/api/coding/context", { directory: options?.directory, workspace_id: options?.workspace_id }),
    );
  },

  listWorkspaceFiles(directory?: string, options?: { workspace_id?: string | null }) {
    return request<{ files: CodingContextEntry[] }>(
      withQuery("/api/coding/files", { directory, workspace_id: options?.workspace_id }),
    );
  },

  readWorkspaceFile(path: string, options?: { workspace_id?: string | null }) {
    return request<{
      path: string;
      content: string;
      size?: number;
      encoding?: string;
      workspace_id?: string | null;
      workspace_root?: string | null;
    }>("/api/coding/files/read", {
      method: "POST",
      body: JSON.stringify({ path, workspace_id: options?.workspace_id }),
    });
  },

  getGitBranch(options?: { workspace_id?: string | null }) {
    return request<CodingBranchResponse>(
      withQuery("/api/coding/git/branch", { workspace_id: options?.workspace_id }),
    );
  },

  switchGitBranch(branch: string, create = false, options?: { workspace_id?: string | null }) {
    return request<CodingBranchResponse>("/api/coding/git/branch", {
      method: "POST",
      body: JSON.stringify({ action: "switch", branch, create, workspace_id: options?.workspace_id }),
    });
  },

  listCodingWorkspaces() {
    return request<CodingWorkspacesResponse>("/api/coding/workspaces", { cache: "no-store" });
  },

  getCodingWorkspace(workspaceId: string) {
    return request<{ workspace: CodingWorkspaceRecord }>(
      withQuery("/api/coding/workspaces/get", { workspace_id: workspaceId }),
      { cache: "no-store" },
    );
  },

  createCodingWorkspace(payload: {
    root_path?: string;
    workspace_root?: string;
    label?: string;
    workspace_id?: string;
    trusted?: boolean;
    metadata?: Record<string, unknown>;
  }) {
    return request<{ workspace: CodingWorkspaceRecord }>("/api/coding/workspaces", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  updateCodingWorkspace(workspaceId: string, updates: Partial<CodingWorkspaceRecord> & { workspace_root?: string }) {
    return request<{ workspace: CodingWorkspaceRecord }>("/api/coding/workspaces/update", {
      method: "POST",
      body: JSON.stringify({ workspace_id: workspaceId, ...updates }),
    });
  },

  selectCodingWorkspace(workspaceId: string) {
    return request<{ workspace: CodingWorkspaceRecord; selected_workspace_id: string }>("/api/coding/workspaces/select", {
      method: "POST",
      body: JSON.stringify({ workspace_id: workspaceId }),
    });
  },

  trustCodingWorkspace(workspaceId: string) {
    return request<{ workspace: CodingWorkspaceRecord }>("/api/coding/workspaces/trust", {
      method: "POST",
      body: JSON.stringify({ workspace_id: workspaceId }),
    });
  },

  selectDirectory(prompt?: string) {
    return request<DirectorySelectionResponse>("/api/ui/select-directory", {
      method: "POST",
      body: JSON.stringify({ prompt }),
    });
  },

  prepareChatGroupStorage(rootPath: string) {
    return request<ChatGroupStorageResponse>("/api/chat/group-storage", {
      method: "POST",
      body: JSON.stringify({ root_path: rootPath }),
    });
  },

  getGitStatus(options?: { workspace_id?: string | null }) {
    return request<CodingGitStatus & { workspace_id?: string | null; workspace_root?: string | null }>(
      withQuery("/api/coding/git/status", { workspace_id: options?.workspace_id }),
      { cache: "no-store" },
    );
  },

  getGitDiff(options?: { workspace_id?: string | null; ref?: string | null }) {
    return request<CodingDiffResponse>(
      withQuery("/api/coding/git/diff", { workspace_id: options?.workspace_id, ref: options?.ref }),
      { cache: "no-store" },
    );
  },

  runTerminalCommand(command: string, options?: {
    workspace_id?: string | null;
    cwd?: string | null;
    timeout?: number;
    approval_token?: string;
  }) {
    return request<CodingTerminalResponse>("/api/coding/terminal/exec", {
      method: "POST",
      body: JSON.stringify({ command, ...(options ?? {}) }),
    });
  },

  listCodingApprovals(options?: { status?: string; include_expired?: boolean; limit?: number }) {
    return request<{ requests: CodingApprovalRequest[]; pending: CodingApprovalRequest[]; count: number }>(
      withQuery("/api/coding/approvals", {
        status: options?.status,
        include_expired: options?.include_expired,
        limit: options?.limit,
      }),
      { cache: "no-store" },
    );
  },

  approveCodingApproval(requestId: string) {
    return request<CodingApprovalDecision>("/api/coding/approvals/approve", {
      method: "POST",
      body: JSON.stringify({ approval_request_id: requestId }),
    });
  },

  denyCodingApproval(requestId: string, reason?: string) {
    return request<Record<string, unknown>>("/api/coding/approvals/deny", {
      method: "POST",
      body: JSON.stringify({ approval_request_id: requestId, reason }),
    });
  },

  listCodingCheckpoints(options?: { workspace_id?: string | null; limit?: number }) {
    return request<{ checkpoints: CodingCheckpoint[]; workspace_id?: string | null; workspace_root?: string | null }>(
      withQuery("/api/coding/checkpoints", { workspace_id: options?.workspace_id, limit: options?.limit }),
      { cache: "no-store" },
    );
  },

  createCodingCheckpoint(payload?: {
    workspace_id?: string | null;
    paths?: string[];
    operation?: string;
    metadata?: Record<string, unknown>;
  }) {
    return request<{ checkpoint: CodingCheckpoint; workspace_id?: string | null; workspace_root?: string | null }>(
      "/api/coding/checkpoints",
      {
        method: "POST",
        body: JSON.stringify(payload ?? {}),
      },
    );
  },

  restoreCodingSnapshot(snapshotId: string, options?: {
    workspace_id?: string | null;
    paths?: string[];
    approval_token?: string;
  }) {
    return request<Record<string, unknown>>("/api/coding/files/restore", {
      method: "POST",
      body: JSON.stringify({ snapshot_id: snapshotId, ...(options ?? {}) }),
    });
  },

  listBrowserArtifacts(options?: { session_id?: string; limit?: number }) {
    return request<{ artifacts: BrowserArtifact[]; count: number }>(
      withQuery("/api/browser/artifacts", { session_id: options?.session_id, limit: options?.limit }),
      { cache: "no-store" },
    );
  },

  listMcpServers() {
    return request<{ servers: McpServerRecord[]; count: number }>("/api/tools/mcp", { cache: "no-store" });
  },

  registerMcpServer(server: Partial<McpServerRecord> & { server_id?: string; name?: string; config?: Record<string, unknown> }) {
    return request<{ server: McpServerRecord }>("/api/tools/mcp", {
      method: "POST",
      body: JSON.stringify({ server }),
    });
  },

  connectMcpServer(payload: {
    server_id?: string;
    server_name?: string;
    config?: Record<string, unknown>;
    approval_token?: string;
  }) {
    return request<Record<string, unknown>>("/api/tools/mcp/connect", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  createCodingAgentSession(payload: {
    task: string;
    workspace_id?: string | null;
    agents?: Array<Record<string, unknown>>;
    metadata?: Record<string, unknown>;
  }) {
    return request<{ session: CodingAgentSession; merge_report?: Record<string, unknown> }>(
      "/api/coding/agent/sessions",
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
  },

  getCodingAgentSessionStatus(sessionId: string) {
    return request<CodingAgentSession>(
      withQuery("/api/coding/agent/sessions/status", { session_id: sessionId }),
      { cache: "no-store" },
    );
  },

  getCodingAgentMergeReport(sessionId: string) {
    return request<{ session_id: string; merge_report: Record<string, unknown> }>(
      withQuery("/api/coding/agent/sessions/merge-report", { session_id: sessionId }),
      { cache: "no-store" },
    );
  },
};
