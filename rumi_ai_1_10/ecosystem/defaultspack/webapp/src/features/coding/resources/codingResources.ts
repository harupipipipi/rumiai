import {
  api,
  defaultspackApiFetch,
  explainDefaultspackApiError,
} from "../../../lib/api";

export type McpLifecycleResult = {
  approval_required?: boolean;
  approval_request_id?: string;
  approval_request?: { request_id?: string };
  server_id?: string;
  server_name?: string;
  status?: string;
  connected?: boolean;
  deleted?: boolean;
  removed_tools?: string[];
};

type ApiEnvelope<T> =
  | { status: "ok"; data: T }
  | { status: "error"; error: { code?: string; message?: string } };

async function mcpLifecycleRequest(
  path: string,
  method: "POST" | "DELETE",
  payload: {
    server_id: string;
    workspace_id?: string | null;
    approval_token?: string;
  },
): Promise<McpLifecycleResult> {
  const response = await defaultspackApiFetch(path, {
    method,
    body: JSON.stringify(payload),
  });
  let envelope: ApiEnvelope<McpLifecycleResult>;
  try {
    envelope = await response.json() as ApiEnvelope<McpLifecycleResult>;
  } catch {
    throw new Error(explainDefaultspackApiError(response.status, undefined, response.statusText));
  }
  if (!response.ok || envelope.status === "error") {
    throw new Error(explainDefaultspackApiError(
      response.status,
      envelope.status === "error" ? envelope.error : undefined,
      response.statusText,
    ));
  }
  return envelope.data;
}

export const codingResources = {
  listCodingApprovals: api.listCodingApprovals,
  approveCodingApproval: api.approveCodingApproval,
  denyCodingApproval: api.denyCodingApproval,
  listCodingCheckpoints: api.listCodingCheckpoints,
  createCodingCheckpoint: api.createCodingCheckpoint,
  restoreCodingSnapshot: api.restoreCodingSnapshot,
  listRumiLogs: api.listRumiLogs,
  appendRumiLog: api.appendRumiLog,
  seedRumiLogPlan: api.seedRumiLogPlan,
  getGitStatus: api.getGitStatus,
  getGitDiff: api.getGitDiff,
  runTerminalCommand: api.runTerminalCommand,
  listMcpServers: api.listMcpServers,
  registerMcpServer: api.registerMcpServer,
  connectMcpServer: api.connectMcpServer,
  disconnectMcpServer(payload: {
    server_id: string;
    workspace_id?: string | null;
    approval_token?: string;
  }) {
    return mcpLifecycleRequest("/api/tools/mcp/disconnect", "POST", payload);
  },
  removeMcpServer(payload: {
    server_id: string;
    workspace_id?: string | null;
    approval_token?: string;
  }) {
    return mcpLifecycleRequest("/api/tools/mcp", "DELETE", payload);
  },
  listBrowserArtifacts: api.listBrowserArtifacts,
  createCodingAgentSession: api.createCodingAgentSession,
  getCodingAgentSessionStatus: api.getCodingAgentSessionStatus,
};
