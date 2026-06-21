import { defaultspackApiFetch, explainDefaultspackApiError } from "../../lib/api";
import type {
  CreateDesktopRequest,
  DesktopControlLease,
  DesktopFrameQuality,
  DesktopFrameResult,
  DesktopInputRequest,
  DesktopInstance,
  RuntimeDoctorResult,
  RuntimeOperation,
  RuntimeProvidersResponse,
  SandboxInstance,
  SandboxTemplate,
} from "./types";

type ApiEnvelope<T> =
  | { status: "ok"; data: T }
  | { status: "error"; error: { code?: string; message?: string } };

function encodeId(value: string): string {
  return encodeURIComponent(value);
}

function requestId(prefix: string): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await defaultspackApiFetch(path, init);
  let payload: ApiEnvelope<T>;
  try {
    payload = await response.json() as ApiEnvelope<T>;
  } catch {
    throw new Error(explainDefaultspackApiError(response.status, undefined, response.statusText));
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

function numberHeader(response: Response, names: string[], fallback: number): number {
  for (const name of names) {
    const raw = response.headers.get(name);
    if (!raw) continue;
    const parsed = Number(raw);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

function stringHeader(response: Response, names: string[], fallback: string | null = null): string | null {
  for (const name of names) {
    const value = response.headers.get(name);
    if (value && value.trim()) return value.trim();
  }
  return fallback;
}

export async function fetchDesktopFrame(
  seatId: string,
  options: {
    afterSeq?: number | null;
    quality?: DesktopFrameQuality;
    signal?: AbortSignal;
  } = {},
): Promise<DesktopFrameResult> {
  const query = new URLSearchParams();
  if (typeof options.afterSeq === "number") query.set("after", String(options.afterSeq));
  if (options.quality) query.set("quality", options.quality);

  const suffix = query.toString() ? `?${query.toString()}` : "";
  const response = await defaultspackApiFetch(`/api/desktops/${encodeId(seatId)}/frame${suffix}`, {
    method: "GET",
    headers: {
      Accept: "image/webp,image/jpeg,image/png",
    },
    cache: "no-store",
    signal: options.signal,
  });

  if (response.status === 204) {
    return { status: "not_modified", seat_id: seatId, after_seq: options.afterSeq ?? null };
  }
  if (!response.ok) {
    throw new Error(explainDefaultspackApiError(response.status, undefined, response.statusText));
  }

  const blob = await response.blob();
  const fallbackSeq = typeof options.afterSeq === "number" ? options.afterSeq + 1 : 0;
  return {
    status: "frame",
    seat_id: seatId,
    frame_seq: numberHeader(response, ["X-Rumi-Frame-Seq", "X-Frame-Seq"], fallbackSeq),
    width: numberHeader(response, ["X-Rumi-Frame-Width", "X-Frame-Width"], 0),
    height: numberHeader(response, ["X-Rumi-Frame-Height", "X-Frame-Height"], 0),
    mime_type: response.headers.get("Content-Type")?.split(";")[0]?.trim() || blob.type || "image/jpeg",
    blob,
    captured_at: stringHeader(response, ["X-Rumi-Captured-At", "X-Captured-At"]),
  };
}

export const sandboxesApi = {
  listRuntimeProviders() {
    return request<RuntimeProvidersResponse>("/api/runtime/providers", { cache: "no-store" });
  },

  runRuntimeDoctor() {
    return request<RuntimeDoctorResult>("/api/runtime/doctor", {
      method: "POST",
      body: JSON.stringify({ request_id: requestId("doctor") }),
    });
  },

  ensureRuntime(providerId?: string | null) {
    return request<RuntimeOperation>("/api/runtime/ensure", {
      method: "POST",
      body: JSON.stringify({
        request_id: requestId("ensure"),
        provider_id: providerId || undefined,
      }),
    });
  },

  getRuntimeOperation(operationId: string) {
    return request<RuntimeOperation>(`/api/runtime/operations/${encodeId(operationId)}`, { cache: "no-store" });
  },

  listSandboxTemplates() {
    return request<{ templates: SandboxTemplate[] }>("/api/sandbox/templates", { cache: "no-store" });
  },

  listSandboxes() {
    return request<{ sandboxes: SandboxInstance[] }>("/api/sandboxes", { cache: "no-store" });
  },

  listDesktops() {
    return request<{ desktops: DesktopInstance[] }>("/api/desktops", { cache: "no-store" });
  },

  createDesktop(payload: CreateDesktopRequest) {
    return request<DesktopInstance>("/api/desktops", {
      method: "POST",
      body: JSON.stringify({
        ...payload,
        request_id: payload.request_id ?? requestId("desktop-create"),
      }),
    });
  },

  startDesktop(seatId: string) {
    return request<DesktopInstance>(`/api/desktops/${encodeId(seatId)}/start`, {
      method: "POST",
      body: JSON.stringify({ request_id: requestId("desktop-start") }),
    });
  },

  stopDesktop(seatId: string) {
    return request<DesktopInstance>(`/api/desktops/${encodeId(seatId)}/stop`, {
      method: "POST",
      body: JSON.stringify({ request_id: requestId("desktop-stop") }),
    });
  },

  restartDesktop(seatId: string) {
    return request<DesktopInstance>(`/api/desktops/${encodeId(seatId)}/restart`, {
      method: "POST",
      body: JSON.stringify({ request_id: requestId("desktop-restart") }),
    });
  },

  deleteDesktop(seatId: string) {
    return request<{ deleted: boolean; seat_id: string }>(`/api/desktops/${encodeId(seatId)}`, {
      method: "DELETE",
      body: JSON.stringify({ request_id: requestId("desktop-delete") }),
    });
  },

  fetchDesktopFrame,

  acquireDesktopControl(seatId: string) {
    return request<DesktopControlLease>(`/api/desktops/${encodeId(seatId)}/control/acquire`, {
      method: "POST",
      body: JSON.stringify({ request_id: requestId("desktop-control-acquire") }),
    });
  },

  renewDesktopControl(seatId: string, leaseToken: string) {
    return request<DesktopControlLease>(`/api/desktops/${encodeId(seatId)}/control/renew`, {
      method: "POST",
      body: JSON.stringify({
        lease_token: leaseToken,
        request_id: requestId("desktop-control-renew"),
      }),
    });
  },

  releaseDesktopControl(seatId: string, leaseToken: string) {
    return request<{ released: boolean; seat_id: string }>(`/api/desktops/${encodeId(seatId)}/control/release`, {
      method: "POST",
      body: JSON.stringify({
        lease_token: leaseToken,
        request_id: requestId("desktop-control-release"),
      }),
    });
  },

  sendDesktopInput(seatId: string, payload: DesktopInputRequest) {
    return request<{ accepted: boolean; seat_id: string }>(`/api/desktops/${encodeId(seatId)}/input`, {
      method: "POST",
      body: JSON.stringify({
        ...payload,
        client_action_id: payload.client_action_id ?? requestId("desktop-action"),
        request_id: payload.request_id ?? requestId("desktop-input"),
      }),
    });
  },
};
