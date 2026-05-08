import type { ToolPreviewItem } from "../components/ToolPreview";

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
  thinking_levels?: string[];
  default_thinking_level?: string | null;
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
  is_archived: boolean;
  current_node_id?: string | null;
  messages: ChatMessage[];
};

export type SidebarCategory = "tool" | "widget" | "system" | "integration" | "capability";

export type SidebarFieldOption = {
  value: string | number | boolean;
  label: string;
};

export type SidebarField = {
  id: string;
  label: string;
  type: "text" | "textarea" | "number" | "toggle" | "select" | "readonly" | "secret" | "api_keys";
  default?: unknown;
  required?: boolean;
  help?: string;
  min?: number;
  max?: number;
  options?: SidebarFieldOption[];
  provider_id?: string;
  configured_field?: string;
  advanced?: boolean;
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

export type SidebarItem = {
  id: string;
  label: string;
  category: SidebarCategory;
  description?: string;
  badge?: string | null;
  tags?: string[];
  risk?: "low" | "medium" | "high" | string | null;
  ui?: ToolUiMetadata;
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
  tool_policy?: Record<string, unknown>;
  attachments?: ChatAttachment[];
  tools?: string[];
  metadata?: Record<string, unknown>;
};

type ChatStreamError = string | { code?: string; message?: string };

export type ChatStreamEvent =
  | { type: "delta"; delta: string }
  | { type: "thinking_delta"; delta: string }
  | { type: "message" | "done" | "user_message"; message?: ChatMessage }
  | { type: "error"; error?: ChatStreamError };

type ChatStreamHandlers = {
  onEvent?: (event: ChatStreamEvent) => void;
  onDelta?: (delta: string) => void;
  onThinkingDelta?: (delta: string) => void;
  onMessage?: (message: ChatMessage) => void;
  onUserMessage?: (message: ChatMessage) => void;
  signal?: AbortSignal;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  let payload: ApiEnvelope<T>;
  try {
    payload = (await response.json()) as ApiEnvelope<T>;
  } catch {
    throw new Error("defaultspack API returned an invalid JSON response");
  }

  if (!response.ok || payload.status === "error") {
    const message =
      payload.status === "error"
        ? payload.error.message
        : `Request failed with status ${response.status}`;
    throw new Error(message);
  }

  return payload.data;
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
      event = JSON.parse(raw) as ChatStreamEvent;
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
  listConversations() {
    return request<{ conversations: Conversation[]; total: number }>(
      "/api/chat/conversations",
    );
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
    const response = await fetch(`/api/chat/conversations/${conversationId}/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(messageRequestBody(text, options)),
      signal: handlers?.signal,
    });

    const contentType = response.headers.get("Content-Type") ?? "";
    if (!response.ok || !contentType.includes("text/event-stream")) {
      let payload: ApiEnvelope<ChatMessage>;
      try {
        payload = (await response.json()) as ApiEnvelope<ChatMessage>;
      } catch {
        throw new Error(`Request failed with status ${response.status}`);
      }
      if (payload.status === "error") {
        throw new Error(payload.error.message);
      }
      handlers?.onMessage?.(payload.data);
      return payload.data;
    }
    return readStreamEvents(response, handlers);
  },

  listModelProfiles() {
    return request<{ profiles: ModelProfile[]; count: number }>("/api/ai/profiles");
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

  saveProviderApiKey(providerId: string, value: string, options?: { apiId?: string; name?: string }) {
    return request<{ provider_id: string; api_id?: string; name?: string; configured: boolean }>("/api/ai/provider-key", {
      method: "POST",
      body: JSON.stringify({
        provider_id: providerId,
        value,
        api_id: options?.apiId,
        name: options?.name,
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

  getBrowserScreenshots(conversationId: string, runId: string) {
    return request<{ screenshots: BrowserScreenshot[] }>(
      `/api/chat/conversations/${conversationId}/run-results/${runId}/browser-screenshots`,
    );
  },

  listSchedules() {
    return request<Record<string, unknown>>("/api/agent/schedules");
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

  triggerSchedule(scheduleId: string) {
    return request<Record<string, unknown>>(`/api/agent/schedules/${scheduleId}/trigger`, {
      method: "POST",
      body: JSON.stringify({}),
    });
  },

  listChannels() {
    return request<Record<string, unknown>>("/api/chat/channels");
  },

  createShare(payload: Record<string, unknown>) {
    return request<Record<string, unknown>>("/api/share", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  getCodingContext(options?: { directory?: string }) {
    const params = new URLSearchParams();
    if (options?.directory) params.set("directory", options.directory);
    return request<CodingContextResponse>(
      `/api/coding/context${params.size ? `?${params.toString()}` : ""}`,
    );
  },

  listWorkspaceFiles(directory?: string) {
    const params = new URLSearchParams();
    if (directory) params.set("directory", directory);
    return request<{ files: CodingContextEntry[] }>(
      `/api/coding/files${params.size ? `?${params.toString()}` : ""}`,
    );
  },

  readWorkspaceFile(path: string) {
    return request<{
      path: string;
      content: string;
      size?: number;
      encoding?: string;
    }>("/api/coding/files/read", {
      method: "POST",
      body: JSON.stringify({ path }),
    });
  },

  getGitBranch() {
    return request<CodingBranchResponse>(
      "/api/coding/git/branch",
    );
  },

  switchGitBranch(branch: string, create = false) {
    return request<CodingBranchResponse>("/api/coding/git/branch", {
      method: "POST",
      body: JSON.stringify({ action: "switch", branch, create }),
    });
  },
};
