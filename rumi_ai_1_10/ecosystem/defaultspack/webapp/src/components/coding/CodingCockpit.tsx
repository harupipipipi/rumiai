import { Bot, ChevronDown, ChevronRight, FolderGit2, FolderPlus, Globe2, PlugZap, RefreshCw, RotateCw, ShieldCheck, Trash2, Unplug, Users } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  BrowserArtifact,
  CodingApprovalDecision,
  CodingApprovalRequest,
  CodingAgentSession,
  CodingWorkspaceRecord,
  McpServerRecord,
} from "../../lib/api";
import { codingResources } from "../../features/coding/resources/codingResources";
import { ApprovalQueue } from "./ApprovalQueue";
import { ChangeReviewPanel } from "./ChangeReviewPanel";
import { CheckpointPanel } from "./CheckpointPanel";
import { DiffPanel } from "./DiffPanel";
import { RumiLogPanel } from "./RumiLogPanel";
import { TerminalPanel, type ApprovedTerminalDecision } from "./TerminalPanel";
import {
  approvedMcpRetryReason,
  isMcpApprovalRequest,
  sameMcpDraft,
  type McpConnectionDraft,
  type PendingMcpConnection,
} from "./mcpApproval";

function workspaceLabel(workspace: CodingWorkspaceRecord): string {
  return workspace.label || workspace.workspace_id;
}

export type McpLifecycleAction = "disconnect" | "remove";

export type PendingMcpLifecycle = {
  requestId: string;
  action: McpLifecycleAction;
  serverId: string;
  workspaceId: string | null;
};

export type McpServerDetailRow = {
  label: string;
  value: string;
};

const MCP_SECRET_NAME = /(?:api[_-]?key|authorization|cookie|credential|password|secret|token)/i;

function serverRecord(server: McpServerRecord): Record<string, unknown> {
  return server as unknown as Record<string, unknown>;
}

function objectRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

export function mcpServerIdentifier(server: McpServerRecord): string {
  return String(server.server_id || server.server_name || server.name || "").trim();
}

function mcpServerConfig(server: McpServerRecord): Record<string, unknown> {
  const record = serverRecord(server);
  return objectRecord(record.registered_config ?? server.config);
}

function safeMcpEndpoint(value: unknown): string {
  const text = typeof value === "string" ? value.trim() : "";
  if (!text) return "";
  if (!/^[A-Za-z][A-Za-z0-9+.-]*:\/\//.test(text)) {
    return text.slice(0, 240);
  }
  try {
    const url = new URL(text);
    url.username = "";
    url.password = "";
    url.search = "";
    url.hash = "";
    return url.toString();
  } catch {
    return "[invalid endpoint]";
  }
}

export function redactMcpArguments(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const result: string[] = [];
  let redactNext = false;
  for (const raw of value.slice(0, 40)) {
    const argument = String(raw);
    if (redactNext) {
      result.push("[redacted]");
      redactNext = false;
      continue;
    }
    const assignment = argument.match(/^([^=]{1,80})=(.*)$/s);
    if (assignment && MCP_SECRET_NAME.test(assignment[1])) {
      result.push(`${assignment[1]}=[redacted]`);
      continue;
    }
    if (MCP_SECRET_NAME.test(argument) && /^--?[A-Za-z0-9_.-]+$/.test(argument)) {
      result.push(argument);
      redactNext = true;
      continue;
    }
    result.push(safeMcpEndpoint(argument).slice(0, 240));
  }
  return result;
}

export function mcpServerDetailRows(server: McpServerRecord): McpServerDetailRow[] {
  const config = mcpServerConfig(server);
  const transport = String(server.transport || config.transport || "stdio");
  const tools = Array.isArray(server.tools) ? server.tools.map((tool) => String(tool)).filter(Boolean) : [];
  const env = objectRecord(config.env);
  const rows: McpServerDetailRow[] = [
    { label: "State", value: serverPermission(server) },
    { label: "Transport", value: transport },
  ];
  if (transport === "sse") {
    const endpoint = safeMcpEndpoint(config.url);
    if (endpoint) rows.push({ label: "Endpoint", value: endpoint });
  } else {
    const command = String(config.command || "").trim();
    if (command) rows.push({ label: "Command", value: command.slice(0, 240) });
    const args = redactMcpArguments(config.args);
    if (args.length) rows.push({ label: "Arguments", value: args.join(" ") });
    const cwd = String(config.cwd || "").trim();
    if (cwd) rows.push({ label: "Working directory", value: cwd.slice(0, 240) });
  }
  const envKeys = Object.keys(env).filter((key) => key.trim()).slice(0, 40);
  if (envKeys.length) {
    rows.push({ label: "Environment", value: `Configured keys only: ${envKeys.join(", ")}` });
  }
  if (tools.length) rows.push({ label: "Tools", value: tools.slice(0, 20).join(", ") });
  return rows;
}

function serverPermission(server: McpServerRecord): string {
  if (server.connected) return "connected";
  const status = String(server.status || "").trim();
  if (status) return status;
  const permission = server.permissions;
  if (permission && permission.approved === true) return "approved";
  if (permission && permission.approved === false) return "unapproved";
  return "registered";
}

export function isMcpLifecycleApprovalRequest(request: CodingApprovalRequest): boolean {
  return request.operation === "tool.mcp_disconnect" || request.operation === "tool.mcp_remove";
}

export function approvedMcpLifecycleRetryReason(
  pending: PendingMcpLifecycle | null,
  currentWorkspaceId: string | null,
  decision: CodingApprovalDecision,
): string | null {
  if (!pending || pending.requestId !== decision.request_id) {
    return "This MCP lifecycle approval is stale or already settled. Refresh the server and try again.";
  }
  if (pending.workspaceId !== currentWorkspaceId) {
    return "The selected workspace changed after review. Request the MCP action again.";
  }
  if (!decision.approved || !decision.token) {
    return decision.reason || "The MCP lifecycle action was not approved.";
  }
  return null;
}

function approvalRequestId(result: {
  approval_request_id?: string;
  approval_request?: { request_id?: string };
}): string {
  return typeof result.approval_request_id === "string"
    ? result.approval_request_id
    : result.approval_request?.request_id ?? "";
}

function artifactPreview(artifact: BrowserArtifact): string {
  return artifact.url || artifact.text || artifact.action || artifact.artifact_id;
}

function parseMcpArgs(value: string): string[] {
  const trimmed = value.trim();
  if (!trimmed) return [];
  try {
    const parsed = JSON.parse(trimmed) as unknown;
    if (Array.isArray(parsed)) return parsed.map((item) => String(item));
  } catch {
    // fall through to newline mode
  }
  return trimmed.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
}

export function CodingCockpit({
  workspaces,
  selectedWorkspaceId,
  onWorkspaceSelect,
  onWorkspaceCreate,
  onWorkspaceTrust,
  onWorkspacesRefresh,
  consoleScopeKey,
  variant = "sidecar",
}: {
  workspaces: CodingWorkspaceRecord[];
  selectedWorkspaceId?: string | null;
  onWorkspaceSelect?: (workspaceId: string) => void;
  onWorkspaceCreate?: () => void;
  onWorkspaceTrust?: (workspaceId: string) => void;
  onWorkspacesRefresh?: () => void;
  consoleScopeKey?: string;
  variant?: "sidecar" | "sidebar";
}) {
  const selectedWorkspace = useMemo(
    () => workspaces.find((workspace) => workspace.workspace_id === selectedWorkspaceId) ?? workspaces[0] ?? null,
    [selectedWorkspaceId, workspaces],
  );
  const activeWorkspaceId = selectedWorkspace?.workspace_id ?? selectedWorkspaceId ?? null;
  const [mcpServers, setMcpServers] = useState<McpServerRecord[]>([]);
  const [browserArtifacts, setBrowserArtifacts] = useState<BrowserArtifact[]>([]);
  const [sessions, setSessions] = useState<CodingAgentSession[]>([]);
  const [sessionTask, setSessionTask] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [approvedTerminalDecision, setApprovedTerminalDecision] = useState<ApprovedTerminalDecision | null>(null);
  const [mcpServerId, setMcpServerId] = useState("");
  const [mcpCommand, setMcpCommand] = useState("");
  const [mcpArgs, setMcpArgs] = useState("");
  const [mcpBusy, setMcpBusy] = useState(false);
  const [pendingMcp, setPendingMcp] = useState<PendingMcpConnection | null>(null);
  const [pendingMcpLifecycle, setPendingMcpLifecycle] = useState<PendingMcpLifecycle | null>(null);
  const [expandedMcpServerId, setExpandedMcpServerId] = useState<string | null>(null);
  const [removeConfirmServerId, setRemoveConfirmServerId] = useState<string | null>(null);
  const [approvalRefreshKey, setApprovalRefreshKey] = useState(0);
  const [activeCockpitTab, setActiveCockpitTab] = useState<"review" | "workspace">("review");
  const isSidebar = variant === "sidebar";

  const loadSidecarState = useCallback(async () => {
    setStatus(null);
    try {
      const [mcp, artifacts] = await Promise.all([
        codingResources.listMcpServers(),
        codingResources.listBrowserArtifacts({ limit: 8 }),
      ]);
      setMcpServers(mcp.servers);
      setBrowserArtifacts(artifacts.artifacts);
    } catch (err) {
      setStatus(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void loadSidecarState();
  }, [loadSidecarState]);

  useEffect(() => {
    if (!pendingMcp) return;
    if (!sameMcpDraft(pendingMcp.draft, {
      serverId: mcpServerId.trim(),
      command: mcpCommand.trim(),
      args: parseMcpArgs(mcpArgs),
      workspaceId: activeWorkspaceId,
    })) {
      setStatus("MCP configuration or workspace changed. The pending review is stale; connect again for a new review.");
    }
  }, [activeWorkspaceId, mcpArgs, mcpCommand, mcpServerId, pendingMcp]);

  const createSession = async () => {
    const task = sessionTask.trim() || "Inspect workspace changes";
    setStatus(null);
    try {
      const result = await codingResources.createCodingAgentSession({
        task,
        workspace_id: activeWorkspaceId,
        agents: [{ agent_id: "worker", role: "worker", task }],
      });
      setSessions((items) => [result.session, ...items].slice(0, 8));
      setSessionTask("");
    } catch (err) {
      setStatus(err instanceof Error ? err.message : String(err));
    }
  };

  const refreshSessions = async () => {
    const refreshed: CodingAgentSession[] = [];
    for (const session of sessions) {
      try {
        const result = await codingResources.getCodingAgentSessionStatus(session.session_id);
        refreshed.push(result);
      } catch {
        refreshed.push(session);
      }
    }
    setSessions(refreshed);
  };

  const currentMcpDraft = (): McpConnectionDraft => ({
    serverId: mcpServerId.trim(),
    command: mcpCommand.trim(),
    args: parseMcpArgs(mcpArgs),
    workspaceId: activeWorkspaceId,
  });

  const rememberPendingMcp = (requestId: string, draft: McpConnectionDraft) => {
    setPendingMcp({ requestId, draft });
    setApprovalRefreshKey((value) => value + 1);
    setActiveCockpitTab("workspace");
    setStatus(
      `MCP approval required for ${draft.serverId}. Review it in the separate Approvals queue below; ` +
        "the requesting form cannot approve its own request.",
    );
  };

  const finishMcpConnection = async (serverId: string, tools: unknown[]) => {
    setPendingMcp(null);
    setMcpServerId("");
    setMcpCommand("");
    setMcpArgs("");
    await loadSidecarState();
    setStatus(`MCP connected: ${serverId}${tools.length ? ` (${tools.length} tools)` : ""}`);
  };

  const rememberPendingMcpLifecycle = (
    requestId: string,
    action: McpLifecycleAction,
    serverId: string,
  ) => {
    setPendingMcpLifecycle({
      requestId,
      action,
      serverId,
      workspaceId: activeWorkspaceId,
    });
    setApprovalRefreshKey((value) => value + 1);
    setActiveCockpitTab("workspace");
    setStatus(
      `${action === "remove" ? "Removing" : "Disconnecting"} ${serverId} requires approval. ` +
        "Review the separate Approvals queue; this server row cannot approve itself.",
    );
  };

  const runMcpLifecycle = async (
    action: McpLifecycleAction,
    serverId: string,
    approvalToken?: string,
  ) => {
    if (!serverId || mcpBusy) return;
    setMcpBusy(true);
    setStatus(null);
    try {
      const result = action === "disconnect"
        ? await codingResources.disconnectMcpServer({
            server_id: serverId,
            workspace_id: activeWorkspaceId,
            approval_token: approvalToken,
          })
        : await codingResources.removeMcpServer({
            server_id: serverId,
            workspace_id: activeWorkspaceId,
            approval_token: approvalToken,
          });
      const requestId = approvalRequestId(result);
      if (result.approval_required) {
        if (!requestId) throw new Error("MCP lifecycle approval response did not include a request id");
        rememberPendingMcpLifecycle(requestId, action, serverId);
        return;
      }
      setPendingMcpLifecycle(null);
      setRemoveConfirmServerId(null);
      if (action === "remove" && expandedMcpServerId === serverId) {
        setExpandedMcpServerId(null);
      }
      await loadSidecarState();
      setStatus(action === "remove" ? `MCP registration removed: ${serverId}` : `MCP disconnected: ${serverId}`);
    } catch (err) {
      setApprovalRefreshKey((value) => value + 1);
      setStatus(`MCP ${action} failed. The registration remains visible for recovery. ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setMcpBusy(false);
    }
  };

  const reconnectMcpServer = async (server: McpServerRecord) => {
    const serverId = mcpServerIdentifier(server);
    if (!serverId || mcpBusy) return;
    const config = mcpServerConfig(server);
    const command = String(config.command || "").trim();
    const args = Array.isArray(config.args) ? config.args.map((item) => String(item)) : [];
    const draft: McpConnectionDraft = {
      serverId,
      command,
      args,
      workspaceId: activeWorkspaceId,
    };
    setMcpServerId(serverId);
    setMcpCommand(command);
    setMcpArgs(args.join("\n"));
    setMcpBusy(true);
    setStatus(null);
    try {
      const result = await codingResources.connectMcpServer({
        server_id: serverId,
        workspace_id: activeWorkspaceId,
      });
      const requestId = approvalRequestId(result);
      if (result.approval_required) {
        if (!requestId) throw new Error("MCP approval response did not include a request id");
        rememberPendingMcp(requestId, draft);
        return;
      }
      await finishMcpConnection(serverId, Array.isArray(result.tools) ? result.tools : []);
    } catch (err) {
      setStatus(`MCP reconnect failed. The saved registration was not removed. ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setMcpBusy(false);
    }
  };

  const handleApprovalApproved = async (decision: CodingApprovalDecision, request: CodingApprovalRequest) => {
    if (request.operation === "terminal.exec") {
      setApprovedTerminalDecision({
        request_id: decision.request_id,
        approved: decision.approved,
        token: decision.token,
        nonce: Date.now(),
      });
      return;
    }
    if (isMcpLifecycleApprovalRequest(request)) {
      const retryReason = approvedMcpLifecycleRetryReason(
        pendingMcpLifecycle,
        activeWorkspaceId,
        decision,
      );
      if (retryReason) {
        setPendingMcpLifecycle(null);
        setApprovalRefreshKey((value) => value + 1);
        setStatus(retryReason);
        return;
      }
      if (!pendingMcpLifecycle || !decision.token || mcpBusy) return;
      const approvedAttempt = pendingMcpLifecycle;
      setPendingMcpLifecycle(null);
      await runMcpLifecycle(
        approvedAttempt.action,
        approvedAttempt.serverId,
        decision.token,
      );
      return;
    }
    if (!isMcpApprovalRequest(request)) return;
    const draft = currentMcpDraft();
    const retryReason = approvedMcpRetryReason(pendingMcp, draft, decision);
    if (retryReason) {
      setPendingMcp(null);
      setApprovalRefreshKey((value) => value + 1);
      setStatus(retryReason);
      return;
    }
    if (!pendingMcp || !decision.token || mcpBusy) return;

    // Clear first so a double click or a repeated settlement cannot replay the token.
    const approvedAttempt = pendingMcp;
    setPendingMcp(null);
    setMcpBusy(true);
    setStatus(`Starting approved MCP server: ${approvedAttempt.draft.serverId}`);
    try {
      const result = await codingResources.connectMcpServer({
        server_id: approvedAttempt.draft.serverId,
        workspace_id: approvedAttempt.draft.workspaceId,
        approval_token: decision.token,
      });
      const nextRequestId = typeof result.approval_request_id === "string"
        ? result.approval_request_id
        : result.approval_request?.request_id;
      if (result.approval_required && nextRequestId) {
        rememberPendingMcp(nextRequestId, approvedAttempt.draft);
        return;
      }
      await finishMcpConnection(
        approvedAttempt.draft.serverId,
        Array.isArray(result.tools) ? result.tools : [],
      );
    } catch (err) {
      setApprovalRefreshKey((value) => value + 1);
      setStatus(`MCP start or reconnect failed. Review the configuration and try again. ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setMcpBusy(false);
    }
  };

  const handleApprovalDenied = (request: CodingApprovalRequest) => {
    if (isMcpLifecycleApprovalRequest(request)) {
      if (pendingMcpLifecycle?.requestId !== request.request_id) return;
      const deniedAction = pendingMcpLifecycle.action;
      setPendingMcpLifecycle(null);
      setRemoveConfirmServerId(null);
      setStatus(`MCP ${deniedAction} denied. The current registration and process state are unchanged.`);
      return;
    }
    if (!isMcpApprovalRequest(request) || pendingMcp?.requestId !== request.request_id) return;
    setPendingMcp(null);
    setStatus("MCP connection denied. You can edit the configuration and connect again.");
  };

  const connectMcpServer = async () => {
    const serverId = mcpServerId.trim();
    const command = mcpCommand.trim();
    if (!serverId || !command || mcpBusy) return;
    setMcpBusy(true);
    setStatus(null);
    try {
      const draft = currentMcpDraft();
      const config = {
        server_id: serverId,
        name: serverId,
        transport: "stdio",
        command,
        args: draft.args,
      };
      await codingResources.registerMcpServer({ server_id: serverId, name: serverId, config });
      const result = await codingResources.connectMcpServer({
        server_id: serverId,
        workspace_id: activeWorkspaceId,
      });
      const requestId = typeof result.approval_request_id === "string"
        ? result.approval_request_id
        : result.approval_request?.request_id;
      if (result.approval_required) {
        if (!requestId) throw new Error("MCP approval response did not include a request id");
        rememberPendingMcp(requestId, draft);
        return;
      }
      await finishMcpConnection(serverId, Array.isArray(result.tools) ? result.tools : []);
    } catch (err) {
      setStatus(err instanceof Error ? err.message : String(err));
    } finally {
      setMcpBusy(false);
    }
  };

  return (
    <aside
      className={
        isSidebar
          ? "coding-cockpit flex h-full min-h-[520px] w-full flex-col overflow-hidden rounded-2xl border border-zinc-800/80 bg-[#0b0b0f]/95 shadow-[0_18px_46px_rgba(0,0,0,0.28)]"
          : "coding-cockpit flex w-[410px] max-w-[42vw] flex-shrink-0 flex-col overflow-hidden border-l border-zinc-800/60 bg-[#0b0b0f] max-[1180px]:hidden"
      }
      aria-label={isSidebar ? "Coding widget" : "Coding cockpit"}
    >
      <div className="border-b border-zinc-800/60 p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <FolderGit2 size={15} className="text-zinc-300" />
            <h1 className="truncate text-sm font-semibold text-zinc-100">{isSidebar ? "Coding widget" : "Coding Cockpit"}</h1>
          </div>
          <button
            type="button"
            onClick={() => {
              onWorkspacesRefresh?.();
              void loadSidecarState();
            }}
            className="flex h-7 w-7 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-800 hover:text-zinc-100"
            title="Refresh cockpit"
          >
            <RefreshCw size={13} />
          </button>
        </div>
        <select
          value={selectedWorkspace?.workspace_id ?? ""}
          onChange={(event) => event.target.value && onWorkspaceSelect?.(event.target.value)}
          className="h-8 w-full rounded-md border border-zinc-800 bg-zinc-950/50 px-2 font-mono text-[11px] text-zinc-300 outline-none"
        >
          {workspaces.map((workspace) => (
            <option key={workspace.workspace_id} value={workspace.workspace_id} className="bg-zinc-900 text-zinc-100">
              {workspaceLabel(workspace)}
            </option>
          ))}
          {workspaces.length === 0 && <option value="">no workspace</option>}
        </select>
        <div className="mt-2 grid grid-cols-2 gap-1.5">
          <button
            type="button"
            onClick={onWorkspaceCreate}
            className="flex h-7 min-w-0 items-center justify-center gap-1.5 rounded-md border border-zinc-800 px-2 text-[11px] text-zinc-400 transition hover:border-zinc-700 hover:bg-zinc-900 hover:text-zinc-100"
            title="Add workspace"
          >
            <FolderPlus size={12} className="shrink-0" />
            <span className="truncate">Add</span>
          </button>
          <button
            type="button"
            onClick={() => activeWorkspaceId && onWorkspaceTrust?.(activeWorkspaceId)}
            disabled={!activeWorkspaceId || selectedWorkspace?.trusted === true}
            className="flex h-7 min-w-0 items-center justify-center gap-1.5 rounded-md border border-zinc-800 px-2 text-[11px] text-zinc-400 transition hover:border-zinc-700 hover:bg-zinc-900 hover:text-zinc-100 disabled:cursor-not-allowed disabled:opacity-45"
            title="Trust workspace"
          >
            <ShieldCheck size={12} className="shrink-0" />
            <span className="truncate">{selectedWorkspace?.trusted ? "Trusted" : "Trust"}</span>
          </button>
        </div>
        {status && <p className="mt-2 rounded border border-red-500/30 bg-red-500/10 px-2 py-1 text-[11px] text-red-200">{status}</p>}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="sticky top-0 rumi-layer-panel border-b border-zinc-800/60 bg-[#0b0b0f]/95 p-2 backdrop-blur">
          <div className="grid grid-cols-2 gap-1 rounded-md border border-zinc-800 bg-black/20 p-0.5">
            <button
              type="button"
              onClick={() => setActiveCockpitTab("review")}
              className={`h-7 rounded px-2 text-[11px] font-semibold ${
                activeCockpitTab === "review" ? "bg-zinc-800 text-zinc-100" : "text-zinc-500 hover:bg-zinc-900 hover:text-zinc-300"
              }`}
            >
              Rumi Review
            </button>
            <button
              type="button"
              onClick={() => setActiveCockpitTab("workspace")}
              className={`h-7 rounded px-2 text-[11px] font-semibold ${
                activeCockpitTab === "workspace" ? "bg-zinc-800 text-zinc-100" : "text-zinc-500 hover:bg-zinc-900 hover:text-zinc-300"
              }`}
            >
              Workspace
            </button>
          </div>
        </div>

        <div hidden={activeCockpitTab !== "review"}>
          <ChangeReviewPanel workspaceId={activeWorkspaceId} />
        </div>

        <div hidden={activeCockpitTab !== "workspace"}>
          <RumiLogPanel workspaceId={activeWorkspaceId} />
          <ApprovalQueue
            refreshKey={approvalRefreshKey}
            onApproved={handleApprovalApproved}
            onDenied={handleApprovalDenied}
          />
          <DiffPanel workspaceId={activeWorkspaceId} />
          <CheckpointPanel workspaceId={activeWorkspaceId} />
          <TerminalPanel
            workspaceId={activeWorkspaceId}
            approvedDecision={approvedTerminalDecision}
            storageKey={`rumi-terminal-logs:${consoleScopeKey ?? activeWorkspaceId ?? "default"}`}
          />

          <section className="border-b border-zinc-800/60 p-3" aria-label="Browser artifacts">
            <div className="mb-2 flex items-center gap-2">
              <Globe2 size={14} className="text-cyan-300" />
              <h2 className="truncate text-xs font-semibold uppercase tracking-wide text-zinc-400">Browser</h2>
            </div>
            <div className="space-y-2">
              {browserArtifacts.map((artifact) => (
                <div key={artifact.artifact_id} className="rounded-md border border-zinc-800 bg-black/30 p-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-[11px] text-zinc-300">{artifact.action}</span>
                    <span className="font-mono text-[10px] text-zinc-600">{artifact.session_id}</span>
                  </div>
                  {artifact.screenshot?.data_url ? (
                    <img src={artifact.screenshot.data_url} alt="" className="mt-2 max-h-36 w-full rounded border border-zinc-800 object-contain" />
                  ) : (
                    <p className="mt-1 truncate text-[10px] text-zinc-600">{artifactPreview(artifact)}</p>
                  )}
                </div>
              ))}
              {browserArtifacts.length === 0 && <p className="py-3 text-center text-[11px] text-zinc-600">No browser artifacts</p>}
            </div>
          </section>

          <section className="border-b border-zinc-800/60 p-3" aria-label="MCP servers">
            <div className="mb-2 flex items-center gap-2">
              <PlugZap size={14} className="text-violet-300" />
              <h2 className="truncate text-xs font-semibold uppercase tracking-wide text-zinc-400">MCP</h2>
            </div>
            <div className="mb-3 grid gap-1.5 rounded-md border border-zinc-800 bg-zinc-950/40 p-2">
              <input
                aria-label="MCP server id"
                value={mcpServerId}
                onChange={(event) => setMcpServerId(event.target.value)}
                className="h-7 rounded-md border border-zinc-800 bg-black/30 px-2 font-mono text-[11px] text-zinc-300 outline-none"
                placeholder="server id"
                disabled={mcpBusy}
              />
              <input
                aria-label="MCP command"
                value={mcpCommand}
                onChange={(event) => setMcpCommand(event.target.value)}
                className="h-7 rounded-md border border-zinc-800 bg-black/30 px-2 font-mono text-[11px] text-zinc-300 outline-none"
                placeholder="command"
                disabled={mcpBusy}
              />
              <textarea
                aria-label="MCP args"
                value={mcpArgs}
                onChange={(event) => setMcpArgs(event.target.value)}
                className="min-h-12 resize-none rounded-md border border-zinc-800 bg-black/30 px-2 py-1 font-mono text-[11px] text-zinc-300 outline-none"
                placeholder="args, one per line or JSON array"
                disabled={mcpBusy}
              />
              <button
                type="button"
                onClick={() => void connectMcpServer()}
                disabled={mcpBusy || !mcpServerId.trim() || !mcpCommand.trim()}
                className="h-7 rounded-md bg-zinc-100 px-2 text-[11px] font-semibold text-zinc-950 hover:bg-white disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-600"
                title="Connect MCP server"
              >
                {mcpBusy ? "Connecting..." : "Connect MCP"}
              </button>
            </div>
            <div className="space-y-1.5">
              {mcpServers.map((server) => {
                const serverId = mcpServerIdentifier(server);
                const expanded = expandedMcpServerId === serverId;
                const confirmRemove = removeConfirmServerId === serverId;
                const rows = mcpServerDetailRows(server);
                return (
                  <div key={serverId} className="rounded-md border border-zinc-800 bg-zinc-950/40">
                    <button
                      type="button"
                      aria-expanded={expanded}
                      aria-controls={`mcp-server-details-${serverId}`}
                      onClick={() => setExpandedMcpServerId(expanded ? null : serverId)}
                      className="flex w-full items-center gap-2 px-2 py-2 text-left"
                    >
                      {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                      <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-zinc-300">
                        {server.name || server.server_name || server.server_id}
                      </span>
                      <span className="flex-shrink-0 text-[10px] text-zinc-500">
                        {serverPermission(server)}
                      </span>
                    </button>
                    {expanded && (
                      <div id={`mcp-server-details-${serverId}`} className="border-t border-zinc-800 px-2 pb-2 pt-2">
                        <dl className="grid gap-1.5">
                          {rows.map((row) => (
                            <div key={row.label} className="grid grid-cols-[92px_minmax(0,1fr)] gap-2 text-[10px]">
                              <dt className="text-zinc-600">{row.label}</dt>
                              <dd className="break-all font-mono text-zinc-300">{row.value}</dd>
                            </div>
                          ))}
                        </dl>
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          <button
                            type="button"
                            onClick={() => void reconnectMcpServer(server)}
                            disabled={mcpBusy}
                            className="inline-flex h-7 items-center gap-1 rounded border border-zinc-700 px-2 text-[10px] text-zinc-300 hover:bg-zinc-800 disabled:opacity-40"
                            title={`Reconnect ${serverId}`}
                          >
                            <RotateCw size={11} />
                            Reconnect
                          </button>
                          {server.connected && (
                            <button
                              type="button"
                              onClick={() => void runMcpLifecycle("disconnect", serverId)}
                              disabled={mcpBusy}
                              className="inline-flex h-7 items-center gap-1 rounded border border-amber-500/30 px-2 text-[10px] text-amber-200 hover:bg-amber-500/10 disabled:opacity-40"
                              title={`Disconnect ${serverId}`}
                            >
                              <Unplug size={11} />
                              Disconnect
                            </button>
                          )}
                          {!confirmRemove ? (
                            <button
                              type="button"
                              onClick={() => setRemoveConfirmServerId(serverId)}
                              disabled={mcpBusy}
                              className="inline-flex h-7 items-center gap-1 rounded border border-red-500/30 px-2 text-[10px] text-red-200 hover:bg-red-500/10 disabled:opacity-40"
                              title={`Remove ${serverId}`}
                            >
                              <Trash2 size={11} />
                              Remove
                            </button>
                          ) : (
                            <>
                              <button
                                type="button"
                                onClick={() => void runMcpLifecycle("remove", serverId)}
                                disabled={mcpBusy}
                                className="inline-flex h-7 items-center gap-1 rounded bg-red-500/20 px-2 text-[10px] font-semibold text-red-100 hover:bg-red-500/30 disabled:opacity-40"
                              >
                                <Trash2 size={11} />
                                Confirm remove
                              </button>
                              <button
                                type="button"
                                onClick={() => setRemoveConfirmServerId(null)}
                                disabled={mcpBusy}
                                className="h-7 rounded border border-zinc-700 px-2 text-[10px] text-zinc-400 hover:bg-zinc-800 disabled:opacity-40"
                              >
                                Cancel
                              </button>
                            </>
                          )}
                        </div>
                        {confirmRemove && (
                          <p role="alert" className="mt-2 text-[10px] leading-4 text-red-200">
                            Removing disconnects the process, removes projected tools, and deletes the saved registration.
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
              {mcpServers.length === 0 && <p className="py-3 text-center text-[11px] text-zinc-600">No MCP servers</p>}
            </div>
          </section>

          <section className="p-3" aria-label="Agent sessions">
            <div className="mb-2 flex items-center gap-2">
              <Users size={14} className="text-lime-300" />
              <h2 className="truncate text-xs font-semibold uppercase tracking-wide text-zinc-400">Agents</h2>
              <button
                type="button"
                onClick={() => void refreshSessions()}
                className="ml-auto flex h-7 w-7 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-800 hover:text-zinc-100"
                title="Refresh sessions"
              >
                <RefreshCw size={13} />
              </button>
            </div>
            <div className="flex items-center gap-1.5">
              <input
                value={sessionTask}
                onChange={(event) => setSessionTask(event.target.value)}
                className="h-8 min-w-0 flex-1 rounded-md border border-zinc-800 bg-zinc-950/40 px-2 text-[11px] text-zinc-300 outline-none"
                placeholder="Session task"
              />
              <button
                type="button"
                onClick={() => void createSession()}
                className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md bg-zinc-100 text-zinc-950 hover:bg-white"
                title="Start session"
              >
                <Bot size={13} />
              </button>
            </div>
            <div className="mt-2 space-y-1.5">
              {sessions.map((session) => (
                <div key={session.session_id} className="rounded-md border border-zinc-800 bg-zinc-950/40 px-2 py-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="min-w-0 truncate font-mono text-[11px] text-zinc-300">{session.session_id}</span>
                    <span className="flex-shrink-0 text-[10px] text-zinc-600">{session.status}</span>
                  </div>
                  {session.task && <p className="mt-1 truncate text-[10px] text-zinc-600">{session.task}</p>}
                </div>
              ))}
              {sessions.length === 0 && <p className="py-3 text-center text-[11px] text-zinc-600">No agent sessions</p>}
            </div>
          </section>
        </div>
      </div>
    </aside>
  );
}
