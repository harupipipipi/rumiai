import { defaultspackApiFetch } from "../lib/api";

export type AmbientPermissionId = "microphone.capture" | "camera.capture" | "ambient.trigger.dispatch" | string;

export type AmbientPermissionStatus = {
  granted?: boolean;
  status?: string;
  label?: string;
  risk?: string;
  requires_user_grant?: boolean;
  os_permission_hint?: string;
  checked_at?: string | null;
};

export type AmbientServiceStatus = {
  enabled?: boolean;
  status?: "listening" | "denied" | "paused" | string;
  enrolled?: boolean;
  classifier?: string;
  detector?: string;
  action?: string;
  cooldown_ms?: number;
};

export type AmbientStatus = {
  ambient_monitor: {
    enabled: boolean;
    updated_at?: string | null;
    controls?: string[];
  };
  services: {
    voice_wake_monitor: AmbientServiceStatus;
    gesture_wake_monitor: AmbientServiceStatus;
  };
  permissions: {
    rumi: Record<AmbientPermissionId, AmbientPermissionStatus>;
    os: Record<AmbientPermissionId, AmbientPermissionStatus>;
  };
  hooks?: Record<string, { enabled?: boolean; profile?: string }>;
  privacy?: Record<string, unknown>;
  voice_enrollment?: Record<string, unknown> | null;
  last_trigger?: Record<string, unknown> | null;
  audit_tail?: Array<Record<string, unknown>>;
  allowed_actions?: string[];
  input_aliases?: Record<string, string>;
};

export type AmbientEventPayload = {
  source: "microphone" | "camera" | "hook" | string;
  trigger: "voice_wake" | "pinch" | "gesture_choice" | "approval_gesture" | "external_hook" | string;
  event_id?: string;
  confidence?: number;
  duration_ms?: number;
  mode?: "open_input" | "focus_composer" | "enroll_wake_voice" | "dispatch" | "choice_response" | "swipe_approve" | "swipe_reject" | string;
  action_id?: "chat.message" | "run.instruction" | "agent.delegate" | "defaults.console.input" | string;
  conversation_id?: string;
  input_text?: string;
  next_action?: string;
  choice?: 2 | 3 | 4;
  decision?: "approve" | "reject" | string;
  metadata?: Record<string, unknown>;
  audio_embedding?: number[];
  samples?: number[];
  attachments?: Array<Record<string, unknown>>;
};

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await defaultspackApiFetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload?.status === "error") {
    const message = payload?.error?.message || payload?.error || response.statusText;
    throw new Error(String(message || "ambient request failed"));
  }
  return (payload?.data ?? payload) as T;
}

export const ambientTriggerClient = {
  status() {
    return requestJson<AmbientStatus>("/api/ambient/status", { cache: "no-store" });
  },

  startMonitor(options?: { voice_wake?: boolean; gesture_pinch?: boolean }) {
    return requestJson<AmbientStatus>("/api/ambient/monitor/start", {
      method: "POST",
      body: JSON.stringify(options ?? {}),
    });
  },

  stopMonitor() {
    return requestJson<AmbientStatus>("/api/ambient/monitor/stop", {
      method: "POST",
      body: JSON.stringify({}),
    });
  },

  grantPermission(permissionId: AmbientPermissionId, osStatus?: string) {
    return requestJson<AmbientStatus>("/api/ambient/permissions/grant", {
      method: "POST",
      body: JSON.stringify({ permission_id: permissionId, os_status: osStatus }),
    });
  },

  revokePermission(permissionId: AmbientPermissionId) {
    return requestJson<AmbientStatus>("/api/ambient/permissions/revoke", {
      method: "POST",
      body: JSON.stringify({ permission_id: permissionId }),
    });
  },

  checkOsPermissions(statuses: Record<AmbientPermissionId, string>) {
    return requestJson<AmbientStatus>("/api/ambient/permissions/check", {
      method: "POST",
      body: JSON.stringify({ statuses }),
    });
  },

  submitEvent(payload: AmbientEventPayload) {
    return requestJson<Record<string, unknown>>("/api/ambient/events", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
};
