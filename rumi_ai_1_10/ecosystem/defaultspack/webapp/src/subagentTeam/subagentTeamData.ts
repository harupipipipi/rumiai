import type { CompanyAgent, CompanyChannel, CompanyInboxItem, CompanyMessage, CompanyRecord, CompanyRunLink, CompanyTask } from "../lib/api";

export type SubagentThread = {
  type: "channel" | "dm";
  id: string;
};

export type AgentActivity = {
  latestInbox?: CompanyInboxItem;
  latestRun?: CompanyRunLink;
  openInboxCount: number;
  status: string;
};

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
  },
  {
    agent_id: "frontend",
    role_key: "frontend",
    agent_name: "Frontend",
    display_name: "Frontend",
    model: "stub/default",
    allowed_tools: ["file_read", "file_write", "browser"],
    status: "active",
    aliases: ["ui", "react"],
  },
  {
    agent_id: "backend",
    role_key: "backend",
    agent_name: "Backend",
    display_name: "Backend",
    model: "stub/default",
    allowed_tools: ["file_read", "pytest", "api"],
    status: "idle",
    aliases: ["runtime"],
  },
  {
    agent_id: "qa",
    role_key: "qa",
    agent_name: "QA",
    display_name: "QA",
    model: "stub/default",
    allowed_tools: ["browser", "lint", "build"],
    status: "watching",
    aliases: ["review"],
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

export function agentName(agent: CompanyAgent | undefined | null, fallbackId?: string | null): string {
  return agent?.display_name || agent?.agent_name || agent?.role_key || agent?.agent_id || fallbackId || "Agent";
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

export function metadataNumber(metadata: Record<string, unknown> | undefined, key: string): number | null {
  const value = metadata?.[key];
  const numeric = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

export function channelCount(channel: CompanyChannel, messages: CompanyMessage[]): number {
  const unread = metadataNumber(channel.metadata, "unread_count");
  if (unread !== null) return Math.max(0, Math.round(unread));
  if (typeof channel.message_count === "number") return Math.max(0, channel.message_count);
  return messages.filter((message) => message.channel_id === channel.id).length;
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
