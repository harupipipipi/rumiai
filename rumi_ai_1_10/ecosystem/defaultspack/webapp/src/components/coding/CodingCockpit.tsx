import { Bot, FolderGit2, Globe2, PlugZap, RefreshCw, Users } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  api,
  type BrowserArtifact,
  type CodingAgentSession,
  type CodingWorkspaceRecord,
  type McpServerRecord,
} from "../../lib/api";
import { ApprovalQueue } from "./ApprovalQueue";
import { CheckpointPanel } from "./CheckpointPanel";
import { DiffPanel } from "./DiffPanel";
import { TerminalPanel } from "./TerminalPanel";

function workspaceLabel(workspace: CodingWorkspaceRecord): string {
  return workspace.label || workspace.workspace_id;
}

function serverPermission(server: McpServerRecord): string {
  const permission = server.permissions;
  if (permission && permission.approved === true) return "approved";
  if (permission && permission.approved === false) return "unapproved";
  return server.connected ? "connected" : "registered";
}

function artifactPreview(artifact: BrowserArtifact): string {
  return artifact.url || artifact.text || artifact.action || artifact.artifact_id;
}

export function CodingCockpit({
  workspaces,
  selectedWorkspaceId,
  onWorkspaceSelect,
  onWorkspacesRefresh,
}: {
  workspaces: CodingWorkspaceRecord[];
  selectedWorkspaceId?: string | null;
  onWorkspaceSelect?: (workspaceId: string) => void;
  onWorkspacesRefresh?: () => void;
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

  const loadSidecarState = useCallback(async () => {
    setStatus(null);
    try {
      const [mcp, artifacts] = await Promise.all([
        api.listMcpServers(),
        api.listBrowserArtifacts({ limit: 8 }),
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

  const createSession = async () => {
    const task = sessionTask.trim() || "Inspect workspace changes";
    setStatus(null);
    try {
      const result = await api.createCodingAgentSession({
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
        const result = await api.getCodingAgentSessionStatus(session.session_id);
        refreshed.push(result);
      } catch {
        refreshed.push(session);
      }
    }
    setSessions(refreshed);
  };

  return (
    <aside className="coding-cockpit flex w-[410px] max-w-[42vw] flex-shrink-0 flex-col overflow-hidden border-l border-zinc-800/60 bg-[#0b0b0f] max-[1180px]:hidden" aria-label="Coding cockpit">
      <div className="border-b border-zinc-800/60 p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <FolderGit2 size={15} className="text-zinc-300" />
            <h1 className="truncate text-sm font-semibold text-zinc-100">Coding Cockpit</h1>
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
        {status && <p className="mt-2 rounded border border-red-500/30 bg-red-500/10 px-2 py-1 text-[11px] text-red-200">{status}</p>}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <ApprovalQueue />
        <DiffPanel workspaceId={activeWorkspaceId} />
        <CheckpointPanel workspaceId={activeWorkspaceId} />
        <TerminalPanel workspaceId={activeWorkspaceId} />

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
          <div className="space-y-1.5">
            {mcpServers.map((server) => (
              <div key={server.server_id || server.server_name || server.name} className="flex items-center justify-between gap-2 rounded-md border border-zinc-800 bg-zinc-950/40 px-2 py-1.5">
                <span className="min-w-0 truncate font-mono text-[11px] text-zinc-300">{server.name || server.server_name || server.server_id}</span>
                <span className="flex-shrink-0 text-[10px] text-zinc-600">{serverPermission(server)}</span>
              </div>
            ))}
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
    </aside>
  );
}
