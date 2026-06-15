import {
  AlertTriangle,
  Bot,
  Check,
  ChevronDown,
  ClipboardCheck,
  Crown,
  FileText,
  FolderTree,
  Hash,
  History,
  Inbox,
  MessageCircle,
  MessageSquare,
  RefreshCw,
  Send,
  ShieldCheck,
  Sparkles,
  UserRound,
  UsersRound,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";

import { api, arrayFromRecord, type CompanyAgent, type CompanyChannel, type CompanyInboxItem, type CompanyMessage, type CompanyRecord, type CompanyRunLink, type CompanyTask } from "../lib/api";
import { cn } from "../lib/cn";
import {
  agentInitials,
  agentName,
  buildAgentActivity,
  channelCount,
  channelName,
  messageTime,
  messageTimestamp,
  previewAgents,
  previewChannels,
  previewCompany,
  previewInbox,
  previewMessages,
  previewRuns,
  previewTasks,
  shortId,
  type AgentActivity,
  type SubagentThread,
} from "./subagentTeamData";

type TreeMode = "files" | "history" | null;
type DecisionStatus = "waiting" | "approved" | "revision";

type SubagentTeamWorkspaceProps = {
  activeConversationId?: string | null;
  activeConversationTitle?: string | null;
};

const DEFAULT_CHANNEL_ID = "ship-room";

const fileTreeItems = [
  { id: "workspace", depth: 0, label: "workspace", kind: "folder" },
  { id: "src", depth: 1, label: "src", kind: "folder" },
  { id: "team", depth: 2, label: "subagentTeam", kind: "folder" },
  { id: "panel", depth: 3, label: "SubagentTeamWorkspace.tsx", kind: "file" },
  { id: "notes", depth: 1, label: "decision-log.md", kind: "file" },
  { id: "qa", depth: 1, label: "qa-evidence", kind: "folder" },
];

const historyTreeItems = [
  { id: "brief", depth: 0, label: "Creator brief accepted", kind: "event" },
  { id: "pm", depth: 1, label: "PM routed frontend and QA", kind: "event" },
  { id: "ui", depth: 1, label: "Channel/DM shell drafted", kind: "event" },
  { id: "decision", depth: 1, label: "Decision preview awaiting Creator", kind: "event" },
];

function effectiveThreadId(thread: SubagentThread): string {
  return thread.type === "dm" ? `dm-${thread.id}` : thread.id;
}

function senderIcon(senderId: string): ReactNode {
  const normalized = senderId.toLowerCase();
  if (normalized === "creator") return <Crown size={13} />;
  if (normalized === "pm") return <ShieldCheck size={13} />;
  if (normalized === "user" || normalized === "you") return <UserRound size={13} />;
  return <Bot size={13} />;
}

function statusClassName(status: string): string {
  const value = status.toLowerCase();
  if (/(active|running|review|routing)/.test(value)) return "border-emerald-500/25 bg-emerald-500/10 text-emerald-200";
  if (/(queued|pending|waiting)/.test(value)) return "border-amber-500/25 bg-amber-500/10 text-amber-200";
  if (/(error|failed|blocked)/.test(value)) return "border-red-500/25 bg-red-500/10 text-red-200";
  return "border-zinc-800 bg-zinc-950/50 text-zinc-500";
}

function mentionIdsFromText(text: string, agents: CompanyAgent[]): string[] {
  const lower = text.toLowerCase();
  return agents
    .filter((agent) => {
      const ids = [agent.agent_id, agent.display_name, agent.agent_name, ...(agent.aliases ?? [])]
        .map((value) => String(value ?? "").trim().toLowerCase())
        .filter(Boolean);
      return ids.some((id) => lower.includes(`@${id}`));
    })
    .map((agent) => agent.agent_id);
}

function compactCount(value: number): string {
  if (value > 99) return "99+";
  return String(Math.max(0, value));
}

function TreePreview({ mode, onClose }: { mode: Exclude<TreeMode, null>; onClose: () => void }) {
  const items = mode === "files" ? fileTreeItems : historyTreeItems;
  return (
    <div className="mx-2 mb-2 rounded-lg border border-zinc-800/80 bg-zinc-950/65 p-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5 text-[11px] font-medium text-zinc-200">
          {mode === "files" ? <FolderTree size={13} className="text-sky-300" /> : <History size={13} className="text-amber-300" />}
          <span className="truncate">{mode === "files" ? "File tree" : "History tree"}</span>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-500 hover:border-zinc-700 hover:text-zinc-200"
        >
          Close
        </button>
      </div>
      <div className="space-y-0.5">
        {items.map((item) => (
          <button
            key={item.id}
            type="button"
            className="flex h-6 w-full items-center gap-1.5 rounded px-1 text-left text-[11px] text-zinc-400 hover:bg-zinc-900/80 hover:text-zinc-100"
            style={{ paddingLeft: `${4 + item.depth * 12}px` }}
          >
            {item.kind === "folder" ? <FolderTree size={11} className="shrink-0 text-sky-400/80" /> : <FileText size={11} className="shrink-0 text-zinc-500" />}
            <span className="truncate">{item.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function SignalBanner({
  tone,
  icon,
  label,
  text,
}: {
  tone: "rich" | "pm";
  icon: ReactNode;
  label: string;
  text: string;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border px-2.5 py-2",
        tone === "rich"
          ? "border-sky-500/20 bg-sky-500/10 text-sky-100"
          : "border-amber-500/20 bg-amber-500/10 text-amber-100",
      )}
    >
      <div className="mb-0.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide">
        <span className="shrink-0">{icon}</span>
        <span>{label}</span>
      </div>
      <p className="line-clamp-2 text-[11px] leading-relaxed text-zinc-300">{text}</p>
    </div>
  );
}

function CreatorDecisionPreview({
  task,
  status,
  onStatusChange,
}: {
  task: CompanyTask | null;
  status: DecisionStatus;
  onStatusChange: (status: DecisionStatus) => void;
}) {
  const title = task?.title || "Approve PM routing plan";
  const targetAgents = task?.target_agent_ids?.length ? task.target_agent_ids.join(", ") : "pm, frontend, qa";
  return (
    <div className="mx-2 mb-2 rounded-lg border border-zinc-800/80 bg-[#0d0d11] p-2.5">
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-500">
            <ClipboardCheck size={12} className="text-emerald-300" />
            <span>Creator decision preview</span>
          </div>
          <p className="mt-1 line-clamp-2 text-[12px] font-medium leading-snug text-zinc-100">{title}</p>
        </div>
        <span className={cn("shrink-0 rounded border px-1.5 py-0.5 text-[9px]", statusClassName(status))}>
          {status}
        </span>
      </div>
      <div className="grid gap-1.5 text-[10px] text-zinc-500">
        <div className="rounded border border-zinc-800 bg-zinc-950/50 px-2 py-1.5">
          <span className="text-zinc-400">Route:</span> {targetAgents}
        </div>
        <div className="rounded border border-zinc-800 bg-zinc-950/50 px-2 py-1.5">
          <span className="text-zinc-400">Creator sees:</span> PM summary, changed files, and latest channel blockers.
        </div>
      </div>
      <div className="mt-2 flex gap-1.5">
        <button
          type="button"
          onClick={() => onStatusChange("approved")}
          className="flex h-7 min-w-0 flex-1 items-center justify-center gap-1 rounded-md bg-zinc-100 px-2 text-[11px] font-semibold text-zinc-950 hover:bg-white"
        >
          <Check size={12} />
          <span className="truncate">OK</span>
        </button>
        <button
          type="button"
          onClick={() => onStatusChange("revision")}
          className="h-7 min-w-0 flex-1 rounded-md border border-zinc-800 px-2 text-[11px] font-medium text-zinc-300 hover:border-zinc-700 hover:bg-zinc-900"
        >
          Revise
        </button>
      </div>
    </div>
  );
}

function MessageRow({
  message,
  sender,
}: {
  message: CompanyMessage;
  sender?: CompanyAgent;
}) {
  const name = message.sender_id === "user" || message.sender_id === "you" ? "You" : agentName(sender, message.sender_id);
  return (
    <article className="group flex gap-2 rounded-lg px-2 py-2 hover:bg-zinc-900/45">
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-zinc-800 bg-zinc-950 text-zinc-400">
        {senderIcon(message.sender_id)}
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-0.5 flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5">
          <span className="truncate text-[12px] font-semibold text-zinc-100">{name}</span>
          <span className="font-mono text-[9px] text-zinc-600">#{shortId(message.id)}</span>
          <span className="text-[9px] text-zinc-700">{messageTime(message.created_at)}</span>
        </div>
        <p className="whitespace-pre-wrap break-words text-[12px] leading-relaxed text-zinc-300">{message.content}</p>
        {message.attachments && message.attachments.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {message.attachments.slice(0, 3).map((attachment, index) => (
              <span
                key={`${message.id}-${attachment.path ?? attachment.name ?? index}`}
                className="inline-flex max-w-full items-center gap-1 rounded border border-zinc-800 bg-zinc-950/70 px-1.5 py-0.5 text-[10px] text-zinc-400"
              >
                <FileText size={10} className="shrink-0" />
                <span className="truncate">{attachment.name || attachment.path || "attachment"}</span>
              </span>
            ))}
          </div>
        )}
      </div>
    </article>
  );
}

function ChannelButton({
  channel,
  active,
  count,
  onClick,
}: {
  channel: CompanyChannel;
  active: boolean;
  count: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      data-testid={`subagent-channel-${channel.id}`}
      onClick={onClick}
      className={cn(
        "group flex w-full items-center gap-1.5 rounded-md px-1.5 py-1.5 text-left transition-colors",
        active ? "bg-zinc-800 text-zinc-100" : "text-zinc-500 hover:bg-zinc-900 hover:text-zinc-300",
      )}
      title={channel.description || channelName(channel)}
    >
      <Hash size={12} className="shrink-0" />
      <span className="min-w-0 flex-1 truncate text-[11px] font-medium">{channelName(channel)}</span>
      {count > 0 && (
        <span className={cn("shrink-0 rounded px-1 py-0.5 text-[9px] font-semibold", active ? "bg-zinc-950 text-zinc-200" : "bg-zinc-800 text-zinc-400")}>
          {compactCount(count)}
        </span>
      )}
    </button>
  );
}

function AgentAvatar({ agent, active = false }: { agent: CompanyAgent; active?: boolean }) {
  return (
    <span
      className={cn(
        "flex h-6 w-6 shrink-0 items-center justify-center rounded-lg border text-[10px] font-semibold",
        active ? "border-sky-400/40 bg-sky-500/15 text-sky-100" : "border-zinc-800 bg-zinc-950 text-zinc-500",
      )}
    >
      {agentInitials(agent)}
    </span>
  );
}

function AgentDisclosure({
  agent,
  activity,
  expanded,
  activeDm,
  onToggle,
  onOpenDm,
}: {
  agent: CompanyAgent;
  activity?: AgentActivity;
  expanded: boolean;
  activeDm: boolean;
  onToggle: () => void;
  onOpenDm: () => void;
}) {
  const status = activity?.status || agent.status || "idle";
  return (
    <div className={cn("rounded-md border", activeDm ? "border-sky-500/30 bg-sky-500/10" : "border-zinc-800/70 bg-zinc-950/35")}>
      <div className="flex items-center gap-1 p-1">
        <button type="button" onClick={onOpenDm} className="flex min-w-0 flex-1 items-center gap-1.5 rounded px-1 py-1 text-left hover:bg-zinc-900/80">
          <AgentAvatar agent={agent} active={activeDm} />
          <span className="min-w-0 flex-1 truncate text-[11px] font-medium text-zinc-200">{agentName(agent)}</span>
          {activity?.openInboxCount ? (
            <span className="rounded bg-sky-500/15 px-1 text-[9px] font-semibold text-sky-200">{compactCount(activity.openInboxCount)}</span>
          ) : null}
        </button>
        <button
          type="button"
          onClick={onToggle}
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded text-zinc-500 hover:bg-zinc-900 hover:text-zinc-200"
          aria-expanded={expanded}
          title={`Expand ${agentName(agent)}`}
        >
          <ChevronDown size={12} className={cn("transition-transform", expanded && "rotate-180")} />
        </button>
      </div>
      {expanded && (
        <div className="border-t border-zinc-800/70 px-2 py-1.5 text-[10px] text-zinc-500">
          <div className="mb-1 flex items-center justify-between gap-2">
            <span className={cn("rounded border px-1 py-0.5", statusClassName(status))}>{status}</span>
            <span className="font-mono">#{shortId(agent.agent_id)}</span>
          </div>
          <p className="truncate font-mono text-zinc-500">{agent.model || "stub/default"}</p>
          {agent.allowed_tools && agent.allowed_tools.length > 0 && (
            <p className="mt-1 line-clamp-2">tools: {agent.allowed_tools.slice(0, 3).join(", ")}</p>
          )}
        </div>
      )}
    </div>
  );
}

export function SubagentTeamWorkspace({
  activeConversationId = null,
  activeConversationTitle = null,
}: SubagentTeamWorkspaceProps) {
  const [companies, setCompanies] = useState<CompanyRecord[]>([]);
  const [activeCompanyId, setActiveCompanyId] = useState<string | null>(null);
  const [company, setCompany] = useState<CompanyRecord | null>(null);
  const [agents, setAgents] = useState<CompanyAgent[]>([]);
  const [channels, setChannels] = useState<CompanyChannel[]>([]);
  const [messages, setMessages] = useState<CompanyMessage[]>([]);
  const [tasks, setTasks] = useState<CompanyTask[]>([]);
  const [runs, setRuns] = useState<CompanyRunLink[]>([]);
  const [inboxItems, setInboxItems] = useState<CompanyInboxItem[]>([]);
  const [localMessages, setLocalMessages] = useState<CompanyMessage[]>([]);
  const [activeThread, setActiveThread] = useState<SubagentThread>({ type: "channel", id: DEFAULT_CHANNEL_ID });
  const [expandedAgentIds, setExpandedAgentIds] = useState<Set<string>>(() => new Set(["creator", "pm"]));
  const [isAgentsOpen, setIsAgentsOpen] = useState(true);
  const [treeMode, setTreeMode] = useState<TreeMode>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [decisionStatus, setDecisionStatus] = useState<DecisionStatus>("waiting");

  const loadWorkspace = useCallback(async (requestedCompanyId?: string | null) => {
    setBusy(true);
    setError(null);
    try {
      const companyListResult = await api.listCompanies({ limit: 8 }).catch(() => ({ companies: [], total: 0 }));
      const listedCompanies = companyListResult.companies;
      let statusCompany: CompanyRecord | null = null;
      let selectedId = requestedCompanyId ?? null;

      if (activeConversationId) {
        const status = await api.getCompanyStatus({ conversationId: activeConversationId, bootstrap: false });
        statusCompany = status.company ?? null;
        selectedId = requestedCompanyId ?? statusCompany?.id ?? null;
      } else if (!selectedId) {
        selectedId = listedCompanies[0]?.id ?? null;
      }

      setCompanies(listedCompanies);
      setActiveCompanyId(selectedId);
      setCompany(statusCompany ?? (selectedId ? listedCompanies.find((item) => item.id === selectedId) ?? null : null));

      if (!selectedId) {
        setAgents([]);
        setChannels([]);
        setMessages([]);
        setTasks([]);
        setRuns([]);
        setInboxItems([]);
        return;
      }

      const [agentResult, channelResult, taskResult, messageResult, runResult] = await Promise.allSettled([
        api.listCompanyAgents(selectedId),
        api.listCompanyChannels(selectedId),
        api.listCompanyTasks(selectedId),
        api.listCompanyMessages(selectedId, { limit: 100 }),
        api.listCompanyRuns(selectedId, { limit: 80 }),
      ]);

      const nextAgents = agentResult.status === "fulfilled" ? agentResult.value.agents : arrayFromRecord(statusCompany?.agents);
      const nextChannels = channelResult.status === "fulfilled" ? channelResult.value.channels : arrayFromRecord(statusCompany?.channels);
      const nextTasks = taskResult.status === "fulfilled" ? taskResult.value.tasks : arrayFromRecord(statusCompany?.tasks);
      const nextMessages = messageResult.status === "fulfilled" ? messageResult.value.messages : arrayFromRecord(statusCompany?.messages);
      const nextRuns = runResult.status === "fulfilled" ? runResult.value.runs : [];

      setAgents(nextAgents);
      setChannels(nextChannels);
      setTasks(nextTasks);
      setMessages(nextMessages);
      setRuns(nextRuns);

      const inboxResults = await Promise.allSettled(
        nextAgents.map((agent) => api.listCompanyAgentInbox(selectedId, agent.agent_id, { limit: 20 })),
      );
      setInboxItems(inboxResults.flatMap((result) => result.status === "fulfilled" ? result.value.inbox : []));

      setActiveThread((current) => {
        if (current.type === "dm" && nextAgents.some((agent) => agent.agent_id === current.id)) return current;
        if (current.type === "channel" && nextChannels.some((channel) => channel.id === current.id)) return current;
        return { type: "channel", id: nextChannels[0]?.id ?? DEFAULT_CHANNEL_ID };
      });

      const firstRejected = [agentResult, channelResult, messageResult].find((result) => result.status === "rejected") as PromiseRejectedResult | undefined;
      if (firstRejected) {
        setError(firstRejected.reason instanceof Error ? firstRejected.reason.message : "Some team workspace data could not be loaded.");
      }
    } catch (workspaceError) {
      setError(workspaceError instanceof Error ? workspaceError.message : "Team workspace APIs are unavailable.");
      setCompanies([]);
      setActiveCompanyId(null);
      setCompany(null);
      setAgents([]);
      setChannels([]);
      setMessages([]);
      setTasks([]);
      setRuns([]);
      setInboxItems([]);
    } finally {
      setBusy(false);
    }
  }, [activeConversationId]);

  useEffect(() => {
    setActiveCompanyId(null);
    setLocalMessages([]);
    void loadWorkspace(null);
  }, [activeConversationId, loadWorkspace]);

  const isPreviewWorkspace = !activeCompanyId && !company;
  const visibleCompany = company ?? companies.find((item) => item.id === activeCompanyId) ?? previewCompany;
  const visibleAgents = isPreviewWorkspace ? previewAgents : agents;
  const visibleChannels = isPreviewWorkspace ? previewChannels : channels;
  const visibleMessages = isPreviewWorkspace ? previewMessages : messages;
  const visibleTasks = isPreviewWorkspace ? previewTasks : tasks;
  const visibleRuns = isPreviewWorkspace ? previewRuns : runs;
  const visibleInbox = isPreviewWorkspace ? previewInbox : inboxItems;
  const allMessages = useMemo(
    () => [...visibleMessages, ...localMessages].sort((left, right) => messageTimestamp(left.created_at) - messageTimestamp(right.created_at)),
    [localMessages, visibleMessages],
  );
  const agentsById = useMemo(() => new Map(visibleAgents.map((agent) => [agent.agent_id, agent])), [visibleAgents]);
  const channelsById = useMemo(() => new Map(visibleChannels.map((channel) => [channel.id, channel])), [visibleChannels]);
  const activityByAgent = useMemo(() => buildAgentActivity(visibleAgents, visibleInbox, visibleRuns), [visibleAgents, visibleInbox, visibleRuns]);
  const activeChannel = activeThread.type === "channel" ? channelsById.get(activeThread.id) : null;
  const activeAgent = activeThread.type === "dm" ? agentsById.get(activeThread.id) : null;
  const latestDecisionTask = visibleTasks.find((task) => /decision|approve|review/i.test(`${task.title} ${task.status ?? ""}`)) ?? visibleTasks[0] ?? null;

  const threadMessages = useMemo(() => {
    if (activeThread.type === "channel") {
      return allMessages.filter((message) => message.channel_id === activeThread.id);
    }
    const dmChannelId = effectiveThreadId(activeThread);
    const agentId = activeThread.id;
    const agentInboxMessages = visibleInbox
      .filter((item) => item.agent_id === agentId)
      .map((item): CompanyMessage => ({
        id: `inbox-${item.inbox_id}`,
        company_id: item.company_id,
        channel_id: dmChannelId,
        sender_id: item.agent_id,
        content: item.content,
        created_at: item.created_at,
        metadata: item.metadata,
      }));
    const agentRunMessages = visibleRuns
      .filter((run) => run.agent_id === agentId && (run.agent_run?.result_preview || run.agent_run?.error))
      .map((run): CompanyMessage => ({
        id: `run-${run.run_id}`,
        company_id: run.company_id,
        channel_id: dmChannelId,
        sender_id: run.agent_id,
        content: run.agent_run?.result_preview || run.agent_run?.error || run.status,
        created_at: run.agent_run?.updated_at ?? run.updated_at ?? run.created_at,
        metadata: run.metadata,
      }));
    return [
      ...allMessages.filter((message) => (
        message.channel_id === dmChannelId
        || message.sender_id === agentId
        || message.mentions?.includes(agentId)
        || message.handoff?.target_agent_id === agentId
      )),
      ...agentInboxMessages,
      ...agentRunMessages,
    ].sort((left, right) => messageTimestamp(left.created_at) - messageTimestamp(right.created_at));
  }, [activeThread, allMessages, visibleInbox, visibleRuns]);

  const toggleExpandedAgent = (agentId: string) => {
    setExpandedAgentIds((current) => {
      const next = new Set(current);
      if (next.has(agentId)) next.delete(agentId);
      else next.add(agentId);
      return next;
    });
  };

  const bootstrapWorkspace = async () => {
    if (!activeConversationId || busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.bootstrapCompanyWorkspace(
        {
          source: "webapp",
          name: "Subagent Team",
          conversation_id: activeConversationId,
          scope: "conversation",
        },
        { conversationId: activeConversationId, scope: "conversation" },
      );
      setCompany(result.company);
      setActiveCompanyId(result.company.id);
      await loadWorkspace(result.company.id);
    } catch (bootstrapError) {
      setError(bootstrapError instanceof Error ? bootstrapError.message : "Could not create team workspace.");
    } finally {
      setBusy(false);
    }
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const content = draft.trim();
    if (!content || busy) return;
    const now = new Date().toISOString();
    const targetChannelId = activeThread.type === "channel" ? activeThread.id : visibleChannels[0]?.id ?? DEFAULT_CHANNEL_ID;
    const mentions = activeThread.type === "dm" ? [activeThread.id] : mentionIdsFromText(content, visibleAgents);
    const optimistic: CompanyMessage = {
      id: `local-${Date.now()}`,
      company_id: visibleCompany.id,
      channel_id: activeThread.type === "dm" ? effectiveThreadId(activeThread) : targetChannelId,
      sender_id: "you",
      content,
      mentions,
      created_at: now,
      metadata: {
        source: "subagent_team_ui",
        ...(activeThread.type === "dm" ? { dm_agent_id: activeThread.id } : {}),
      },
    };
    setLocalMessages((current) => [...current, optimistic]);
    setDraft("");

    if (isPreviewWorkspace || !activeCompanyId) return;
    setBusy(true);
    setError(null);
    try {
      await api.sendCompanyMessage(activeCompanyId, {
        content,
        channel_id: targetChannelId,
        sender_id: "user",
        mentions,
        metadata: optimistic.metadata,
      });
      await loadWorkspace(activeCompanyId);
    } catch (sendError) {
      setError(sendError instanceof Error ? sendError.message : "Message was kept locally, but backend send failed.");
    } finally {
      setBusy(false);
    }
  };

  const threadTitle = activeThread.type === "dm"
    ? agentName(activeAgent, activeThread.id)
    : channelName(activeChannel, activeThread.id);
  const threadSubtitle = activeThread.type === "dm"
    ? `${activityByAgent.get(activeThread.id)?.status ?? activeAgent?.status ?? "idle"} agent DM`
    : activeChannel?.description || "team channel";

  return (
    <section className="flex h-full min-h-0 flex-col bg-[#0a0a0c] text-zinc-300" aria-label="Subagents team workspace">
      <div className="border-b border-zinc-800/60 px-3 py-2">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <div className="flex min-w-0 items-center gap-1.5">
              <UsersRound size={14} className="shrink-0 text-sky-300" />
              <p className="truncate text-[13px] font-semibold text-zinc-100">Subagents / Teams</p>
            </div>
            <p className="truncate text-[10px] text-zinc-600">
              {activeConversationTitle || visibleCompany.name || activeConversationId || "preview workspace"}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {activeConversationId && isPreviewWorkspace && (
              <button
                type="button"
                onClick={bootstrapWorkspace}
                disabled={busy}
                className="h-7 rounded-md bg-zinc-100 px-2 text-[10px] font-semibold text-zinc-950 hover:bg-white disabled:opacity-40"
              >
                Start
              </button>
            )}
            <button
              type="button"
              onClick={() => void loadWorkspace(activeCompanyId)}
              disabled={busy}
              className="flex h-7 w-7 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-40"
              title="Refresh team workspace"
            >
              <RefreshCw size={13} className={cn(busy && "animate-spin")} />
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="m-2 flex items-start gap-2 rounded-md border border-amber-500/20 bg-amber-500/10 px-2 py-1.5 text-[11px] text-amber-100">
          <AlertTriangle size={13} className="mt-0.5 shrink-0" />
          <span className="min-w-0 break-words">{error}</span>
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <aside className="flex w-[104px] shrink-0 flex-col border-r border-zinc-800/60 bg-[#09090b]" aria-label="Team channels">
          <div className="min-h-0 flex-1 overflow-y-auto p-2">
            <div className="mb-2">
              <div className="mb-1 flex items-center justify-between px-1 text-[10px] font-semibold uppercase tracking-wide text-zinc-600">
                <span>Channels</span>
                <span>{visibleChannels.length}</span>
              </div>
              <div className="space-y-1">
                {visibleChannels.map((channel) => (
                  <ChannelButton
                    key={channel.id}
                    channel={channel}
                    active={activeThread.type === "channel" && activeThread.id === channel.id}
                    count={channelCount(channel, allMessages)}
                    onClick={() => setActiveThread({ type: "channel", id: channel.id })}
                  />
                ))}
                {visibleChannels.length === 0 && (
                  <p className="rounded-md border border-zinc-800 bg-zinc-950/40 px-2 py-2 text-[10px] text-zinc-600">No channels</p>
                )}
              </div>
            </div>

            <div className="mb-2">
              <div className="mb-1 flex items-center justify-between px-1 text-[10px] font-semibold uppercase tracking-wide text-zinc-600">
                <span>DMs</span>
                <span>{visibleAgents.length}</span>
              </div>
              <div className="space-y-1">
                {visibleAgents.slice(0, 6).map((agent) => {
                  const activity = activityByAgent.get(agent.agent_id);
                  const active = activeThread.type === "dm" && activeThread.id === agent.agent_id;
                  return (
                    <button
                      key={agent.agent_id}
                      type="button"
                      data-testid={`subagent-dm-${agent.agent_id}`}
                      onClick={() => setActiveThread({ type: "dm", id: agent.agent_id })}
                      className={cn(
                        "flex w-full items-center gap-1.5 rounded-md px-1.5 py-1.5 text-left",
                        active ? "bg-sky-500/15 text-sky-100 ring-1 ring-sky-500/25" : "text-zinc-500 hover:bg-zinc-900 hover:text-zinc-300",
                      )}
                    >
                      <AgentAvatar agent={agent} active={active} />
                      <span className="min-w-0 flex-1 truncate text-[11px] font-medium">{agentName(agent)}</span>
                      {activity?.openInboxCount ? (
                        <span className="rounded bg-sky-500/15 px-1 text-[9px] font-semibold text-sky-200">{compactCount(activity.openInboxCount)}</span>
                      ) : null}
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <button
                type="button"
                onClick={() => setIsAgentsOpen((value) => !value)}
                className="mb-1 flex w-full items-center justify-between rounded px-1 py-1 text-[10px] font-semibold uppercase tracking-wide text-zinc-600 hover:bg-zinc-900 hover:text-zinc-300"
                aria-expanded={isAgentsOpen}
              >
                <span>Agents</span>
                <ChevronDown size={12} className={cn("transition-transform", isAgentsOpen && "rotate-180")} />
              </button>
              {isAgentsOpen && (
                <div className="space-y-1">
                  {visibleAgents.map((agent) => (
                    <AgentDisclosure
                      key={agent.agent_id}
                      agent={agent}
                      activity={activityByAgent.get(agent.agent_id)}
                      expanded={expandedAgentIds.has(agent.agent_id)}
                      activeDm={activeThread.type === "dm" && activeThread.id === agent.agent_id}
                      onToggle={() => toggleExpandedAgent(agent.agent_id)}
                      onOpenDm={() => setActiveThread({ type: "dm", id: agent.agent_id })}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <div className="border-b border-zinc-800/60 px-2.5 py-2">
            <div className="flex min-w-0 items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="flex min-w-0 items-center gap-1.5">
                  {activeThread.type === "dm" ? <MessageCircle size={14} className="shrink-0 text-sky-300" /> : <Hash size={14} className="shrink-0 text-zinc-400" />}
                  <h2 className="truncate text-[13px] font-semibold text-zinc-100">{threadTitle}</h2>
                </div>
                <p className="mt-0.5 line-clamp-1 text-[10px] text-zinc-600">{threadSubtitle}</p>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <button
                  type="button"
                  onClick={() => setTreeMode((current) => current === "files" ? null : "files")}
                  data-testid="subagent-open-files"
                  className={cn("flex h-7 w-7 items-center justify-center rounded-md border text-zinc-500 hover:text-zinc-100", treeMode === "files" ? "border-sky-500/30 bg-sky-500/10 text-sky-200" : "border-zinc-800 bg-zinc-950/40 hover:bg-zinc-900")}
                  title="Open file tree"
                  aria-pressed={treeMode === "files"}
                >
                  <FolderTree size={13} />
                </button>
                <button
                  type="button"
                  onClick={() => setTreeMode((current) => current === "history" ? null : "history")}
                  data-testid="subagent-open-history"
                  className={cn("flex h-7 w-7 items-center justify-center rounded-md border text-zinc-500 hover:text-zinc-100", treeMode === "history" ? "border-amber-500/30 bg-amber-500/10 text-amber-200" : "border-zinc-800 bg-zinc-950/40 hover:bg-zinc-900")}
                  title="Open history tree"
                  aria-pressed={treeMode === "history"}
                >
                  <History size={13} />
                </button>
              </div>
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto">
            <div className="grid gap-1.5 p-2">
              <SignalBanner
                tone="rich"
                icon={<Sparkles size={12} />}
                label="Rich"
                text="Files, history, task links, and long-form context stay attached to the active room."
              />
              <SignalBanner
                tone="pm"
                icon={<ShieldCheck size={12} />}
                label="PM"
                text="PM summarizes handoffs and queues Creator decisions before subagents fan out."
              />
            </div>
            {treeMode && <TreePreview mode={treeMode} onClose={() => setTreeMode(null)} />}
            <CreatorDecisionPreview task={latestDecisionTask} status={decisionStatus} onStatusChange={setDecisionStatus} />
            <div className="px-1 pb-2">
              {threadMessages.map((message) => (
                <MessageRow key={`${message.channel_id}-${message.id}`} message={message} sender={agentsById.get(message.sender_id)} />
              ))}
              {threadMessages.length === 0 && (
                <div className="mx-1 rounded-lg border border-zinc-800/70 bg-zinc-950/45 px-3 py-5 text-center">
                  <Inbox size={18} className="mx-auto mb-2 text-zinc-600" />
                  <p className="text-[12px] font-medium text-zinc-300">No messages yet</p>
                  <p className="mt-1 text-[10px] text-zinc-600">Send a note or DM an agent to start this lane.</p>
                </div>
              )}
            </div>
          </div>

          <form className="border-t border-zinc-800/60 p-2" onSubmit={handleSubmit}>
            <div className="flex items-end gap-1.5 rounded-lg border border-zinc-800 bg-zinc-950/65 p-1.5 focus-within:border-zinc-600">
              <textarea
                value={draft}
                data-testid="subagent-message-input"
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    event.currentTarget.form?.requestSubmit();
                  }
                }}
                placeholder={activeThread.type === "dm" ? `DM ${threadTitle}` : `Message #${threadTitle}`}
                className="max-h-24 min-h-8 min-w-0 flex-1 resize-none bg-transparent px-1 py-1 text-[12px] leading-relaxed text-zinc-200 outline-none placeholder:text-zinc-700"
                rows={1}
                disabled={busy}
              />
              <button
                type="submit"
                disabled={busy || !draft.trim()}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-zinc-100 text-zinc-950 hover:bg-white disabled:opacity-30"
                title="Send team message"
              >
                <Send size={13} />
              </button>
            </div>
          </form>
        </div>
      </div>
    </section>
  );
}
