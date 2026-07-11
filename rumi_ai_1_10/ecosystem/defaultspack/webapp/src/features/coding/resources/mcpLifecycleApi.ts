import { defaultspackApiFetch, explainDefaultspackApiError } from "../../../lib/api";

export type McpLifecycleAction = "connect" | "disconnect" | "remove";

export type McpLifecycleResult = {
  server_id?: string;
  server_name?: string;
  status?: string;
  tools?: string[];
  removed_tools?: string[];
  deleted?: boolean;
  approval_required?: boolean;
  approval_request_id?: string;
  risk?: string;
};

type ApiEnvelope<T> =
  | { status: "ok"; data: T }
  | { status: "error"; error: { code?: string; message?: string } };

async function request<T>(path: string, init: RequestInit): Promise<T> {
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

function approvalBody(serverId: string, approvalToken?: string): string {
  return JSON.stringify({
    server_id: serverId,
    ...(approvalToken ? { approval_token: approvalToken } : {}),
  });
}

export const mcpLifecycleApi = {
  connect(serverId: string, approvalToken?: string) {
    return request<McpLifecycleResult>("/api/tools/mcp/connect", {
      method: "POST",
      body: approvalBody(serverId, approvalToken),
    });
  },

  disconnect(serverId: string, approvalToken?: string) {
    return request<McpLifecycleResult>("/api/tools/mcp/disconnect", {
      method: "POST",
      body: approvalBody(serverId, approvalToken),
    });
  },

  remove(serverId: string, approvalToken?: string) {
    return request<McpLifecycleResult>("/api/tools/mcp", {
      method: "DELETE",
      body: approvalBody(serverId, approvalToken),
    });
  },
};
