import type { CompanyAgent, CompanyChannel, CompanyInboxItem, CompanyMessage, CompanyRecord, CompanyRunLink, CompanyTask } from "../lib/api";

export type SubagentThread = {
  type: "channel" | "dm";
  id: string;
};

export const SUBAGENT_TEAM_WORKSPACE_SURFACE = "subagent_team_workspace";

export type AgentActivity = {
  latestInbox?: CompanyInboxItem;
  latestRun?: CompanyRunLink;
  openInboxCount: number;
  status: string;
};

export type SubagentTreeMode = "files" | "history";

export type SubagentTreeItemKind = "folder" | "file" | "event";

export type SubagentTreeItem = {
  id: string;
  nodeId: string;
  depth: number;
  label: string;
  kind: SubagentTreeItemKind;
  mode: SubagentTreeMode;
  path?: string;
  size?: number;
  source: "api" | "fallback";
};

export type SubagentTreeState = {
  source: "api" | "fallback";
  files: SubagentTreeItem[];
  history: SubagentTreeItem[];
  workspaceId?: string | null;
};

export type SubagentOpenPreview = {
  nodeId: string;
  mode: SubagentTreeMode;
  title: string;
  kind: SubagentTreeItemKind;
  path?: string;
  content?: string;
  messages?: CompanyMessage[];
  source: "api" | "fallback";
  error?: string;
};

export type SubagentTeamPreviewDataReason = "preview_workspace" | "empty_api_data";

export type SubagentTeamDataSnapshot = {
  activeCompanyId?: string | null;
  company?: CompanyRecord | null;
  agents: readonly CompanyAgent[];
  channels: readonly CompanyChannel[];
  messages: readonly CompanyMessage[];
  tasks: readonly CompanyTask[];
  runs: readonly CompanyRunLink[];
  inboxItems: readonly CompanyInboxItem[];
};

export function subagentTeamPreviewDataReason(snapshot: SubagentTeamDataSnapshot): SubagentTeamPreviewDataReason | null {
  if (!snapshot.activeCompanyId && !snapshot.company) return "preview_workspace";
  const hasLoadedTeamData = snapshot.agents.length > 0
    || snapshot.channels.length > 0
    || snapshot.messages.length > 0
    || snapshot.tasks.length > 0
    || snapshot.runs.length > 0
    || snapshot.inboxItems.length > 0;
  return hasLoadedTeamData ? null : "empty_api_data";
}

export const fallbackFileTreeItems: SubagentTreeItem[] = [
  { id: "workspace", nodeId: "workspace", depth: 0, label: "workspace", kind: "folder", mode: "files", source: "fallback" },
  { id: "src", nodeId: "src", depth: 1, label: "src", kind: "folder", mode: "files", source: "fallback" },
  { id: "team", nodeId: "team", depth: 2, label: "subagentTeam", kind: "folder", mode: "files", source: "fallback" },
  { id: "panel", nodeId: "panel", depth: 3, label: "SubagentTeamWorkspace.tsx", kind: "file", mode: "files", source: "fallback" },
  { id: "notes", nodeId: "notes", depth: 1, label: "decision-log.md", kind: "file", mode: "files", source: "fallback" },
  { id: "qa", nodeId: "qa", depth: 1, label: "qa-evidence", kind: "folder", mode: "files", source: "fallback" },
];

export const fallbackHistoryTreeItems: SubagentTreeItem[] = [
  { id: "brief", nodeId: "brief", depth: 0, label: "Creator brief accepted", kind: "event", mode: "history", source: "fallback" },
  { id: "pm", nodeId: "pm", depth: 1, label: "PM routed frontend and QA", kind: "event", mode: "history", source: "fallback" },
  { id: "ui", nodeId: "ui", depth: 1, label: "Channel/DM shell drafted", kind: "event", mode: "history", source: "fallback" },
  { id: "decision", nodeId: "decision", depth: 1, label: "Decision preview awaiting Creator", kind: "event", mode: "history", source: "fallback" },
];

export function fallbackSubagentTreeState(): SubagentTreeState {
  return {
    source: "fallback",
    files: fallbackFileTreeItems,
    history: fallbackHistoryTreeItems,
  };
}

export function subagentTeamWorkspaceMetadata(metadata: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    ...metadata,
    surface: SUBAGENT_TEAM_WORKSPACE_SURFACE,
    subagent_team: true,
  };
}

export function subagentClientMessageId(metadata: Record<string, unknown> | undefined | null): string | null {
  const value = metadata?.client_message_id;
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

export function subagentMessageClientId(message: Pick<CompanyMessage, "metadata">): string | null {
  return subagentClientMessageId(message.metadata);
}

export function removeReconciledLocalSubagentMessages(
  localMessages: CompanyMessage[],
  serverMessages: CompanyMessage[],
  sentClientMessageId?: string | null,
): CompanyMessage[] {
  const serverClientIds = new Set(
    serverMessages.map(subagentMessageClientId).filter((value): value is string => Boolean(value)),
  );
  const sentId = sentClientMessageId?.trim() || null;
  return localMessages.filter((message) => {
    const clientMessageId = subagentMessageClientId(message);
    if (!clientMessageId) return true;
    if (sentId && clientMessageId === sentId) return false;
    return !serverClientIds.has(clientMessageId);
  });
}

export function hasSubagentTeamWorkspaceMarker(metadata: Record<string, unknown> | undefined | null): boolean {
  return Boolean(
    metadata
    && (metadata.subagent_team === true || metadata.surface === SUBAGENT_TEAM_WORKSPACE_SURFACE),
  );
}

export const previewCompany: CompanyRecord = {
  id: "preview-team",
  name: "Subagent Team",
  description: "Local preview workspace",
  status: "preview",
  agent_count: 5,
  channel_count: 4,
  message_count: 7,
  task_count: 3,
};

export const previewAgents: CompanyAgent[] = [
  {
    agent_id: "creator",
    role_key: "creator",
    agent_name: "Creator",
    display_name: "Creator",
    model: "decision-layer",
    allowed_tools: ["approve_plan", "request_revision"],
    status: "reviewing",
    aliases: ["owner", "decision"],
    metadata: { short_id: "sa-creator-001" },
  },
  {
    agent_id: "pm",
    role_key: "pm",
    agent_name: "PM",
    display_name: "PM",
    model: "stub/default",
    allowed_tools: ["tasks", "routing", "history"],
    status: "routing",
    aliases: ["producer", "handoff"],
    metadata: { short_id: "sa-pm-orion-042" },
  },
  {
    agent_id: "frontend",
    role_key: "coder",
    agent_name: "Frontend",
    display_name: "coder_kai",
    model: "stub/default",
    allowed_tools: ["file_read", "file_write", "browser"],
    status: "active",
    aliases: ["ui", "react"],
    metadata: { short_id: "sa-kai-184" },
  },
  {
    agent_id: "backend",
    role_key: "coder",
    agent_name: "Backend",
    display_name: "coder_mira",
    model: "stub/default",
    allowed_tools: ["file_read", "pytest", "api"],
    status: "idle",
    aliases: ["runtime"],
    metadata: { short_id: "sa-mira-212" },
  },
  {
    agent_id: "qa",
    role_key: "qa",
    agent_name: "QA",
    display_name: "qa_sen",
    model: "stub/default",
    allowed_tools: ["browser", "lint", "build"],
    status: "watching",
    aliases: ["review"],
    metadata: { short_id: "sa-sen-319" },
  },
];

export const previewChannels: CompanyChannel[] = [
  {
    id: "ship-room",
    name: "ship-room",
    description: "Implementation handoffs, blockers, and ready-to-merge notes.",
    members: ["creator", "pm", "frontend", "backend", "qa"],
    message_count: 4,
    metadata: { unread_count: 2, tone: "rich" },
  },
  {
    id: "design-review",
    name: "design-review",
    description: "UI review lane for first viewport, panels, and interaction states.",
    members: ["creator", "pm", "frontend"],
    message_count: 2,
    metadata: { unread_count: 1 },
  },
  {
    id: "decisions",
    name: "decisions",
    description: "Creator approvals and PM summaries.",
    members: ["creator", "pm"],
    message_count: 1,
    metadata: { unread_count: 1 },
  },
  {
    id: "qa-log",
    name: "qa-log",
    description: "Validation notes and evidence links.",
    members: ["pm", "qa", "frontend"],
    message_count: 0,
    metadata: { unread_count: 0 },
  },
];

export const previewMessages: CompanyMessage[] = [
  {
    id: "msg-preview-creator-1",
    company_id: previewCompany.id,
    channel_id: "ship-room",
    sender_id: "creator",
    content: "Decision preview is ready. PM can route the UI plan once the workspace has file/history controls and clear agent ownership.",
    mentions: ["pm", "frontend"],
    created_at: "2026-06-16T09:03:00.000Z",
  },
  {
    id: "msg-preview-pm-1",
    company_id: previewCompany.id,
    channel_id: "ship-room",
    sender_id: "pm",
    content: "Rich lane is open: attach files, keep history visible, and make DM updates readable without leaving the team room.",
    mentions: ["frontend", "qa"],
    created_at: "2026-06-16T09:07:00.000Z",
  },
  {
    id: "msg-preview-frontend-1",
    company_id: previewCompany.id,
    channel_id: "ship-room",
    sender_id: "frontend",
    content: "Working in the right sidebar shell. Channel counts, agent expansion, DMs, and Creator decision preview are the first-pass surface.",
    mentions: ["pm"],
    attachments: [{ name: "subagent-team-panel.tsx", path: "src/subagentTeam/SubagentTeamWorkspace.tsx", mime_type: "text/typescript" }],
    created_at: "2026-06-16T09:11:00.000Z",
  },
  {
    id: "msg-preview-qa-1",
    company_id: previewCompany.id,
    channel_id: "ship-room",
    sender_id: "qa",
    content: "I will check desktop and a narrow panel width after build. No backend or test files should move.",
    mentions: ["frontend"],
    created_at: "2026-06-16T09:15:00.000Z",
  },
  {
    id: "msg-preview-design-1",
    company_id: previewCompany.id,
    channel_id: "design-review",
    sender_id: "creator",
    content: "Keep it product-dense, not a landing page. This should feel like a small team operations room.",
    mentions: ["frontend"],
    created_at: "2026-06-16T09:19:00.000Z",
  },
  {
    id: "msg-preview-decisions-1",
    company_id: previewCompany.id,
    channel_id: "decisions",
    sender_id: "creator",
    content: "Approve if the PM banner is visible, DMs are reachable, and every message carries sender identity plus a short id.",
    mentions: ["pm"],
    created_at: "2026-06-16T09:23:00.000Z",
  },
  {
    id: "msg-preview-dm-pm-1",
    company_id: previewCompany.id,
    channel_id: "dm-pm",
    sender_id: "pm",
    content: "DM lane is private-to-workspace: I can turn a channel message into tasks, then bring the Creator back for signoff.",
    mentions: ["creator"],
    created_at: "2026-06-16T09:27:00.000Z",
  },
];

export const previewTasks: CompanyTask[] = [
  {
    id: "task-preview-creator-decision",
    company_id: previewCompany.id,
    title: "Approve subagent workspace UI direction",
    description: "Creator reviews PM proposal before the team fans out into channel and DM work.",
    target_agent_ids: ["creator", "pm"],
    source: "preview",
    status: "pending_decision",
    created_at: "2026-06-16T09:20:00.000Z",
  },
  {
    id: "task-preview-frontend-panel",
    company_id: previewCompany.id,
    title: "Build Slack-like team panel",
    target_agent_ids: ["frontend"],
    source: "preview",
    status: "in_progress",
    created_at: "2026-06-16T09:08:00.000Z",
  },
  {
    id: "task-preview-qa-pass",
    company_id: previewCompany.id,
    title: "Validate rendered panel and interactions",
    target_agent_ids: ["qa"],
    source: "preview",
    status: "queued",
    created_at: "2026-06-16T09:12:00.000Z",
  },
];

export const previewRuns: CompanyRunLink[] = [
  {
    link_id: "run-link-preview-frontend",
    company_id: previewCompany.id,
    task_id: "task-preview-frontend-panel",
    agent_id: "frontend",
    run_id: "run-preview-frontend",
    status: "active",
    agent_run: {
      status: "active",
      model: "stub/default",
      result_preview: "Panel shell created; fitting dense sidebar layout to existing Tailwind style.",
      updated_at: "2026-06-16T09:31:00.000Z",
    },
    created_at: "2026-06-16T09:10:00.000Z",
  },
  {
    link_id: "run-link-preview-qa",
    company_id: previewCompany.id,
    task_id: "task-preview-qa-pass",
    agent_id: "qa",
    run_id: "run-preview-qa",
    status: "queued",
    agent_run: {
      status: "queued",
      model: "stub/default",
      result_preview: "Waiting for UI build before screenshot pass.",
      updated_at: "2026-06-16T09:32:00.000Z",
    },
    created_at: "2026-06-16T09:12:00.000Z",
  },
];

export const previewInbox: CompanyInboxItem[] = [
  {
    inbox_id: "inbox-preview-pm",
    company_id: previewCompany.id,
    agent_id: "pm",
    kind: "handoff",
    status: "open",
    priority: "high",
    content: "Creator is waiting on the UI decision preview before routing QA.",
    created_at: "2026-06-16T09:29:00.000Z",
  },
  {
    inbox_id: "inbox-preview-frontend",
    company_id: previewCompany.id,
    agent_id: "frontend",
    kind: "mention",
    status: "open",
    priority: "normal",
    content: "Make the team workspace readable at the default sidebar width.",
    created_at: "2026-06-16T09:30:00.000Z",
  },
];

export function shortId(value: string | undefined | null): string {
  const normalized = String(value ?? "").trim();
  if (!normalized) return "----";
  const compact = normalized.replace(/[^a-zA-Z0-9]/g, "");
  return (compact || normalized).slice(-6).padStart(4, "0");
}

function metadataString(metadata: Record<string, unknown> | undefined, ...keys: string[]): string {
  for (const key of keys) {
    const value = metadata?.[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

export function agentShortId(agent: CompanyAgent | undefined | null, fallbackId?: string | null): string {
  const explicit = metadataString(agent?.metadata, "short_id", "shortId", "human_id", "humanId", "alias");
  if (explicit) return explicit;
  const id = agent?.agent_id || agent?.id || fallbackId;
  if (!id) return "sa-unknown";
  const normalized = String(id).trim();
  if (/^sa[-_]/i.test(normalized)) return normalized;
  return `sa-${shortId(normalized)}`;
}

export function agentName(agent: CompanyAgent | undefined | null, fallbackId?: string | null): string {
  return agent?.display_name || agent?.agent_name || agent?.role_key || agent?.agent_id || fallbackId || "Agent";
}

export function agentRoleKey(agent: CompanyAgent | undefined | null, fallbackId?: string | null): string {
  const text = [
    agent?.role_key,
    agent?.agent_name,
    agent?.display_name,
    ...(agent?.aliases ?? []),
    fallbackId,
  ].map((value) => String(value ?? "").toLowerCase()).join(" ");
  if (/(^|\s)(pm|producer|manager|lead|orion)(\s|$)/.test(text)) return "pm";
  if (/creator|decision|owner|lifecycle/.test(text)) return "creator";
  if (/qa|test|tester|sen|quality/.test(text)) return "qa";
  if (/review|reviewer|checker|check|audit/.test(text)) return "reviewer";
  if (/research|researcher|book|source/.test(text)) return "researcher";
  if (/design|designer|artifact|creator/.test(text)) return "creator";
  if (/code|coder|frontend|backend|engineer|dev|kai|mira/.test(text)) return "coder";
  return "agent";
}

export function agentInitials(agent: CompanyAgent | undefined | null, fallbackId?: string | null): string {
  const name = agentName(agent, fallbackId);
  const parts = name.split(/[\s._-]+/).filter(Boolean);
  const initials = parts.length > 1
    ? `${parts[0][0] ?? ""}${parts[1][0] ?? ""}`
    : name.slice(0, 2);
  return initials.toUpperCase();
}

export function channelName(channel: CompanyChannel | undefined | null, fallbackId?: string | null): string {
  return channel?.name || fallbackId || channel?.id || "channel";
}

export function channelMemberCount(channel: CompanyChannel): number {
  return Array.isArray(channel.members) ? channel.members.length : 0;
}

export function metadataNumber(metadata: Record<string, unknown> | undefined, key: string): number | null {
  const value = metadata?.[key];
  const numeric = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

export function channelUnreadCount(channel: CompanyChannel, messages: CompanyMessage[]): number {
  const unread = metadataNumber(channel.metadata, "unread_count");
  if (unread !== null) return Math.max(0, Math.round(unread));
  if (typeof channel.message_count === "number") return Math.max(0, channel.message_count);
  return messages.filter((message) => message.channel_id === channel.id).length;
}

export function channelCount(channel: CompanyChannel, messages: CompanyMessage[]): number {
  return channelUnreadCount(channel, messages);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function recordArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

function firstString(...values: unknown[]): string {
  for (const value of values) {
    const text = typeof value === "string" ? value.trim() : "";
    if (text) return text;
  }
  return "";
}

function firstNumber(...values: unknown[]): number | undefined {
  for (const value of values) {
    const numeric = typeof value === "number" ? value : Number(value);
    if (Number.isFinite(numeric)) return numeric;
  }
  return undefined;
}

function basename(path: string): string {
  const normalized = path.replace(/\\/g, "/").replace(/\/+$/, "");
  return normalized.split("/").filter(Boolean).at(-1) || normalized || ".";
}

function itemDepth(raw: Record<string, unknown>, path: string): number {
  const explicitDepth = firstNumber(raw.depth);
  if (explicitDepth !== undefined) return Math.max(0, Math.round(explicitDepth));
  if (!path || path === ".") return 0;
  return Math.max(0, path.split("/").filter(Boolean).length - 1);
}

function itemKind(raw: Record<string, unknown>, mode: SubagentTreeMode): SubagentTreeItemKind {
  if (mode === "history") return "event";
  const type = firstString(raw.kind, raw.type).toLowerCase();
  if (type === "folder" || type === "dir" || type === "directory") return "folder";
  if (raw.is_dir === true || raw.is_directory === true) return "folder";
  return "file";
}

function normalizeTreeItems(value: unknown, mode: SubagentTreeMode): SubagentTreeItem[] {
  return recordArray(value).map((raw, index) => {
    const path = firstString(raw.path, raw.file_path, raw.relative_path);
    const label = firstString(raw.label, raw.name, raw.title, path ? basename(path) : "", `node-${index + 1}`);
    const nodeId = firstString(raw.node_id, raw.nodeId, raw.id, path, label);
    return {
      id: firstString(raw.id, nodeId, `${mode}-${index}`),
      nodeId,
      depth: itemDepth(raw, path),
      label,
      kind: itemKind(raw, mode),
      mode,
      path: path || undefined,
      size: firstNumber(raw.size),
      source: "api",
    };
  });
}

export function normalizeSubagentTreeResponse(payload: unknown): SubagentTreeState {
  const data = isRecord(payload) ? payload : {};
  const files = normalizeTreeItems(
    data.files ?? data.file_tree ?? data.tree ?? data.nodes ?? data.items,
    "files",
  );
  const history = normalizeTreeItems(
    data.history ?? data.history_tree ?? data.events ?? data.conversations,
    "history",
  );
  return {
    source: "api",
    files,
    history,
    workspaceId: firstString(data.workspace_id, data.workspaceId) || null,
  };
}

function normalizePreviewMessages(value: unknown, fallback: SubagentTreeItem): CompanyMessage[] | undefined {
  const messages = recordArray(value).map((raw, index): CompanyMessage => ({
    id: firstString(raw.id, raw.message_id, `${fallback.nodeId}-${index}`),
    company_id: firstString(raw.company_id, "subagent-team"),
    channel_id: firstString(raw.channel_id, raw.thread_id, fallback.nodeId),
    sender_id: firstString(raw.sender_id, raw.sender, raw.role, "history"),
    content: firstString(raw.content, raw.text, raw.message, raw.preview),
    created_at: firstString(raw.created_at, raw.timestamp),
    metadata: isRecord(raw.metadata) ? raw.metadata : undefined,
  })).filter((message) => message.content);
  return messages.length ? messages : undefined;
}

export function normalizeSubagentOpenPreview(payload: unknown, fallback: SubagentTreeItem): SubagentOpenPreview {
  const data = isRecord(payload) ? payload : {};
  const content = firstString(
    data.content,
    data.file_content,
    data.text,
    data.preview,
    data.body,
    data.markdown,
  );
  return {
    nodeId: firstString(data.node_id, data.nodeId, data.id, fallback.nodeId),
    mode: fallback.mode,
    title: firstString(data.title, data.label, data.name, data.path, fallback.label),
    kind: fallback.kind,
    path: firstString(data.path, data.file_path, fallback.path) || undefined,
    content: content || undefined,
    messages: normalizePreviewMessages(data.messages ?? data.history ?? data.conversation, fallback),
    source: "api",
  };
}

export function fallbackSubagentOpenPreview(item: SubagentTreeItem, error?: string): SubagentOpenPreview {
  return {
    nodeId: item.nodeId,
    mode: item.mode,
    title: item.label,
    kind: item.kind,
    path: item.path,
    content: item.kind === "folder" ? undefined : `${item.label} preview`,
    source: "fallback",
    error,
  };
}

export function subagentTreeItemsForMode(state: SubagentTreeState, mode: SubagentTreeMode): SubagentTreeItem[] {
  return mode === "files" ? state.files : state.history;
}

export function buildAgentActivity(agents: CompanyAgent[], inboxItems: CompanyInboxItem[], runs: CompanyRunLink[]): Map<string, AgentActivity> {
  const map = new Map<string, AgentActivity>();
  for (const agent of agents) {
    map.set(agent.agent_id, {
      openInboxCount: 0,
      status: agent.status || "idle",
    });
  }
  for (const run of runs) {
    const current = map.get(run.agent_id) ?? { openInboxCount: 0, status: "idle" };
    map.set(run.agent_id, {
      ...current,
      latestRun: current.latestRun ?? run,
      status: run.status || run.agent_run?.status || current.status,
    });
  }
  for (const item of inboxItems) {
    const current = map.get(item.agent_id) ?? { openInboxCount: 0, status: "idle" };
    map.set(item.agent_id, {
      ...current,
      latestInbox: current.latestInbox ?? item,
      openInboxCount: current.openInboxCount + (item.status === "consumed" ? 0 : 1),
    });
  }
  return map;
}

export function messageTime(value: string | undefined): string {
  if (!value) return "now";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "now";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function messageTimestamp(value: string | undefined): number {
  if (!value) return Date.now();
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : Date.now();
}
