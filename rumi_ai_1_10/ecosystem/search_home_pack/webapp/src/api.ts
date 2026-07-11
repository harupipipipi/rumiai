import type { RouteDecision, RouteSessionState } from "./routerTypes";

export const MODEL_SETTINGS_KEY = "preferred" + "_model";

export type SearchHomeModel = {
  profile_id: string;
  qualified_model_id?: string;
  label?: string;
  display_name?: string;
  provider_display_name?: string;
  provider_id?: string;
  model_id?: string;
  configured?: boolean;
  local?: boolean;
  requires_api_key?: boolean;
  supports_tool_calling?: boolean;
  supports_image_input?: boolean;
  supports_vision?: boolean;
  supports_thinking?: boolean;
  supports_fast?: boolean;
  speed_tier?: string;
  quality_tier?: string;
  knowledge_level?: number;
  availability?: {
    status?: string;
    configured?: boolean;
    active?: boolean;
    available?: boolean;
    [key: string]: unknown;
  };
  metadata?: Record<string, unknown>;
};

export type ModelsResponse = {
  models: SearchHomeModel[];
  filters_applied?: Record<string, unknown>;
};

export type ModelSettingsResponse = {
  models?: Record<string, unknown>;
};

export type SearchAnswerResponse = {
  status: "ok" | "error";
  answer?: string;
  model?: string;
  conversation_id?: string;
  used_tools?: string[];
  used_defaultspack_node?: boolean;
  defaultspack_node?: string;
  tool_calling_unavailable_reason?: string;
  error?: {
    code?: string;
    message?: string;
  };
};

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = (await response.json()) as { error?: { message?: string } };
      if (payload?.error?.message) {
        message = payload.error.message;
      }
    } catch {
      // Ignore malformed error payloads and surface the HTTP status instead.
    }
    throw new Error(message);
  }
  return (await response.json()) as T;
}

export async function routeInput(input: string, model = ""): Promise<RouteDecision> {
  return requestJson<RouteDecision>("/api/route", {
    method: "POST",
    body: JSON.stringify({ input, model }),
  });
}

export async function answerInput(input: string, model = ""): Promise<SearchAnswerResponse> {
  return requestJson<SearchAnswerResponse>("/api/answer", {
    method: "POST",
    body: JSON.stringify({ input, model, use_search: true }),
  });
}

export async function loadModels(): Promise<ModelsResponse> {
  return requestJson<ModelsResponse>("/api/models");
}

export async function loadModelSettings(): Promise<ModelSettingsResponse> {
  return requestJson<ModelSettingsResponse>("/api/settings");
}

export async function setPreferredModel(model: string): Promise<void> {
  await requestJson<unknown>("/api/settings/model", {
    method: "POST",
    body: JSON.stringify({ model }),
  });
}

export async function loadRouteState(): Promise<Record<string, unknown> | null> {
  try {
    return await requestJson<Record<string, unknown>>("/api/route-state");
  } catch {
    return null;
  }
}

export function persistRouteStateRemotely(state: RouteSessionState): void {
  const payload = JSON.stringify(state);
  if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
    const blob = new Blob([payload], { type: "application/json" });
    if (navigator.sendBeacon("/api/route-state", blob)) {
      return;
    }
  }
  void fetch("/api/route-state", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload,
    keepalive: true,
  }).catch(() => undefined);
}

export function clearRouteStateRemotely(): void {
  persistRouteStateRemotely({
    query: "",
    target_url: "",
    fallback_url: "",
    selected_index: -1,
    target_candidates: [],
    updated_at: new Date().toISOString(),
  });
}
