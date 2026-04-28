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
};

export type Conversation = {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
  model: string;
  system_prompt_id?: string | null;
  agent_id?: string | null;
  tags: string[];
  is_starred: boolean;
  is_archived: boolean;
  current_node_id?: string | null;
  messages: ChatMessage[];
};

export type SidebarCategory = "tool" | "widget" | "system" | "integration";

export type SidebarFieldOption = {
  value: string | number | boolean;
  label: string;
};

export type SidebarField = {
  id: string;
  label: string;
  type: "text" | "textarea" | "number" | "toggle" | "select" | "readonly" | "secret";
  default?: unknown;
  required?: boolean;
  help?: string;
  min?: number;
  max?: number;
  options?: SidebarFieldOption[];
  provider_id?: string;
  configured_field?: string;
};

export type SidebarItem = {
  id: string;
  label: string;
  category: SidebarCategory;
  description?: string;
  badge?: string | null;
  tags?: string[];
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
  };
};

export type SettingsSection = {
  id: string;
  label: string;
  description?: string;
  fields: SidebarField[];
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

export const api = {
  listConversations() {
    return request<{ conversations: Conversation[]; total: number }>(
      "/api/chat/conversations",
    );
  },

  getConversation(id: string) {
    return request<Conversation>(`/api/chat/conversations/${id}`);
  },

  createConversation(options?: { model?: string; system_prompt_id?: string | null; agent_id?: string | null; tags?: string[] }) {
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

  sendMessage(conversationId: string, text: string) {
    return request<ChatMessage>(
      `/api/chat/conversations/${conversationId}/messages`,
      {
        method: "POST",
        body: JSON.stringify({
          message: {
            role: "user",
            content: text,
          },
        }),
      },
    );
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

  updateUiSettings(values: Record<string, Record<string, unknown>>) {
    return request<{ values: Record<string, Record<string, unknown>> }>("/api/ui/settings", {
      method: "PUT",
      body: JSON.stringify({ values }),
    });
  },

  saveProviderApiKey(providerId: string, value: string) {
    return request<{ provider_id: string; configured: boolean }>("/api/ai/provider-key", {
      method: "POST",
      body: JSON.stringify({ provider_id: providerId, value }),
    });
  },

  conversationPreview(conversationId: string) {
    return request<{ conversation_id: string; previews: ToolPreviewItem[]; summary: Record<string, number> }>(
      `/api/ui/conversations/${conversationId}/preview`,
    );
  },
};
