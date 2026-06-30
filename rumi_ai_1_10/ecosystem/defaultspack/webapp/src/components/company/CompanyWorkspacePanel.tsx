import { AlertTriangle, Bot, ClipboardList, MessageSquare, Route, Settings, Share2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  CompanyAgent,
  CompanyChannel,
  CompanyInboxItem,
  CompanyInboundRoute,
  CompanyMessage,
  CompanyRecord,
  CompanyRunLink,
  CompanyTask,
  P2PIdentity,
  P2PPeer,
  P2PStatusResponse,
} from "../../lib/api";
import { arrayFromRecord, companyResources } from "../../features/company/resources/companyResources";
import { CompanyAgentList } from "./CompanyAgentList";
import { CompanyChannelView } from "./CompanyChannelView";
import { CompanyInboundRoutesPanel } from "./CompanyInboundRoutesPanel";
import { CompanyP2PPanel } from "./CompanyP2PPanel";
import { CompanySettingsPanel } from "./CompanySettingsPanel";
import { CompanyTaskBoard } from "./CompanyTaskBoard";
import { CompanyTree } from "./CompanyTree";

type CompanyTab = "tasks" | "channels" | "agents" | "routes" | "settings" | "p2p";

const TABS: Array<{ id: CompanyTab; label: string; icon: typeof ClipboardList }> = [
  { id: "tasks", label: "Tasks", icon: ClipboardList },
  { id: "channels", label: "Channels", icon: MessageSquare },
  { id: "agents", label: "Employees", icon: Bot },
  { id: "routes", label: "Routes", icon: Route },
  { id: "settings", label: "Settings", icon: Settings },
  { id: "p2p", label: "P2P", icon: Share2 },
];

const PRIMARY_TAB_IDS = new Set<CompanyTab>(["tasks", "channels", "agents"]);
const PRIMARY_TABS = TABS.filter((tab) => PRIMARY_TAB_IDS.has(tab.id));
const OVERFLOW_TABS = TABS.filter((tab) => !PRIMARY_TAB_IDS.has(tab.id));
export const MIMO_CODING_COMPANY_ID = "mimo-coding-company";
export const OPERATIONS_COMPANY_ID = "operations-company";

function textValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

export function companyIdFromHint(value: unknown): string | null {
  const text = textValue(value);
  if (!text) return null;
  const companyPrefix = "company:";
  if (text.toLowerCase().startsWith(companyPrefix)) {
    return text.slice(companyPrefix.length).trim() || null;
  }
  return text;
}

export function companyIdFromGroupHint(value: unknown): string | null {
  const text = textValue(value);
  if (!text) return null;
  const companyPrefix = "company:";
  if (text.toLowerCase().startsWith(companyPrefix)) {
    return text.slice(companyPrefix.length).trim() || null;
  }
  return null;
}

export function companyIdFromConversationTitle(value: unknown): string | null {
  const text = textValue(value).toLowerCase();
  if (!text) return null;
  const withoutGroupPrefix = text.startsWith("company:") ? text.slice("company:".length).trim() : text;
  const normalized = withoutGroupPrefix.startsWith("[stale] ") ? withoutGroupPrefix.slice("[stale] ".length).trim() : withoutGroupPrefix;
  if (normalized === "mimo coding company" || normalized.startsWith("mimo coding company:")) {
    return MIMO_CODING_COMPANY_ID;
  }
  if (normalized === "operations company" || normalized.startsWith("operations company:")) {
    return OPERATIONS_COMPANY_ID;
  }
  return null;
}

export function resolveCompanyWorkspaceHint({
  companyId,
  groupId,
  conversationKind,
  profileId,
  tags,
}: {
  companyId?: unknown;
  groupId?: unknown;
  conversationKind?: unknown;
  profileId?: unknown;
  tags?: unknown;
}): string | null {
  const directCompanyId = companyIdFromHint(companyId);
  if (directCompanyId) return directCompanyId;
  const groupedCompanyId = companyIdFromGroupHint(groupId);
  if (groupedCompanyId) return groupedCompanyId;

  const kind = textValue(conversationKind);
  const profile = textValue(profileId);
  const tagList = Array.isArray(tags) ? tags.map((tag) => textValue(tag)).filter(Boolean) : [];
  if (kind === "mimo_coding_company" || profile === "defaultspack.mimo_coding_company" || tagList.includes(MIMO_CODING_COMPANY_ID)) {
    return MIMO_CODING_COMPANY_ID;
  }
  if (kind === "operations_company" || profile === "defaultspack.operations_company" || tagList.includes(OPERATIONS_COMPANY_ID)) {
    return OPERATIONS_COMPANY_ID;
  }
  return null;
}

type CompanyHintChat = {
  companyId?: unknown;
  conversationKind?: unknown;
  metadata?: Record<string, unknown> | null;
  tags?: unknown;
};

type CompanyHintGroup = {
  id?: unknown;
  sourceGroupId?: unknown;
  chats?: CompanyHintChat[];
  subGroups?: CompanyHintGroup[];
};

export function resolveCompanyWorkspaceHintFromGroup(group: CompanyHintGroup | null | undefined): string | null {
  if (!group) return null;
  const groupCompanyId = companyIdFromGroupHint(group.sourceGroupId) ?? companyIdFromGroupHint(group.id);
  if (groupCompanyId) return groupCompanyId;

  for (const chat of group.chats ?? []) {
    const metadata = chat.metadata && typeof chat.metadata === "object" ? chat.metadata : {};
    const resolved = resolveCompanyWorkspaceHint({
      companyId: chat.companyId ?? metadata.company_id ?? metadata.companyId,
      groupId: metadata.group_id ?? metadata.groupId,
      conversationKind: chat.conversationKind,
      profileId: metadata.profile_id,
      tags: chat.tags,
    });
    if (resolved) return resolved;
  }

  for (const subGroup of group.subGroups ?? []) {
    const resolved = resolveCompanyWorkspaceHintFromGroup(subGroup);
    if (resolved) return resolved;
  }
  return null;
}

export function resolveActiveChannelId(
  currentChannelId: string | null | undefined,
  channels: Pick<CompanyChannel, "id">[],
  fallbackChannelId = "ops-company",
): string {
  const current = textValue(currentChannelId);
  if (current && channels.some((channel) => channel.id === current)) return current;
  if (channels.some((channel) => channel.id === fallbackChannelId)) return fallbackChannelId;
  return channels[0]?.id || fallbackChannelId;
}

export function resolveCompanyMessageListOptions(
  channels: Pick<CompanyChannel, "id">[],
  resolvedChannelId: string,
): { channel_id?: string; limit: number; tail: true } {
  const options = { limit: 80, tail: true as const };
  if (channels.some((channel) => channel.id === resolvedChannelId)) {
    return { ...options, channel_id: resolvedChannelId };
  }
  return options;
}

export function resolveSelectedCompanyId({
  activeConversationId,
  activeCompanyId,
  hintedCompanyId,
  statusCompany,
  companies,
}: {
  activeConversationId?: string | null;
  activeCompanyId?: string | null;
  hintedCompanyId?: string | null;
  statusCompany?: CompanyRecord | null;
  companies: CompanyRecord[];
}): string | null {
  const normalizedHint = companyIdFromHint(hintedCompanyId);
  if (normalizedHint) return normalizedHint;
  const statusCompanyTitleHint = companyIdFromConversationTitle(statusCompany?.name);
  if (statusCompanyTitleHint) return statusCompanyTitleHint;
  if (activeConversationId) return statusCompany?.id ?? null;
  return activeCompanyId ?? companies[0]?.id ?? statusCompany?.id ?? null;
}

export function resolveEffectiveCompanies({
  activeConversationId,
  activeCompanyIdHint,
  activeCompany,
  companies,
}: {
  activeConversationId?: string | null;
  activeCompanyIdHint?: string | null;
  activeCompany?: CompanyRecord | null;
  companies: CompanyRecord[];
}): CompanyRecord[] {
  const normalizedHint = companyIdFromHint(activeCompanyIdHint);
  if (!activeCompany) return companies;
  const ordered = [activeCompany, ...companies.filter((item) => item.id !== activeCompany.id)];
  if (activeConversationId && !normalizedHint) return ordered;
  return ordered;
}

function researchSources(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object" && !Array.isArray(item))).slice(0, 5);
}

function researchTaskDescription(query: string, sources: Array<Record<string, unknown>>): string {
  const lines = [
    "Deep research request delegated from the president chat.",
    `Search query: ${query}`,
  ];
  if (sources.length > 0) {
    lines.push("", "DuckDuckGo sources:");
    sources.forEach((source, index) => {
      lines.push(`${index + 1}. ${textValue(source.title) || textValue(source.url) || "Untitled source"}`);
      if (textValue(source.url)) lines.push(`   ${textValue(source.url)}`);
      if (textValue(source.summary)) lines.push(`   ${textValue(source.summary)}`);
    });
  } else {
    lines.push("", "DuckDuckGo returned no sources. Continue with explicit uncertainty.");
  }
  return lines.join("\n");
}

function settledErrorMessage(label: string, result: PromiseSettledResult<unknown>): string | null {
  if (result.status !== "rejected") return null;
  const detail = result.reason instanceof Error ? result.reason.message : "unavailable";
  return `${label}: ${detail}`;
}

export function CompanyWorkspacePanel({
  activeConversationId = null,
  activeConversationTitle = null,
  activeCompanyIdHint = null,
}: {
  activeConversationId?: string | null;
  activeConversationTitle?: string | null;
  activeCompanyIdHint?: string | null;
}) {
  const [companies, setCompanies] = useState<CompanyRecord[]>([]);
  const [activeCompanyId, setActiveCompanyId] = useState<string | null>(() => companyIdFromHint(activeCompanyIdHint));
  const [company, setCompany] = useState<CompanyRecord | null>(null);
  const [agents, setAgents] = useState<CompanyAgent[]>([]);
  const [channels, setChannels] = useState<CompanyChannel[]>([]);
  const [messages, setMessages] = useState<CompanyMessage[]>([]);
  const [tasks, setTasks] = useState<CompanyTask[]>([]);
  const [runs, setRuns] = useState<CompanyRunLink[]>([]);
  const [inboxItems, setInboxItems] = useState<CompanyInboxItem[]>([]);
  const [routes, setRoutes] = useState<CompanyInboundRoute[]>([]);
  const [p2pStatus, setP2PStatus] = useState<P2PStatusResponse | null>(null);
  const [p2pIdentity, setP2PIdentity] = useState<P2PIdentity | null>(null);
  const [peers, setPeers] = useState<P2PPeer[]>([]);
  const [activeChannelId, setActiveChannelId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<CompanyTab>("tasks");
  const [isMoreMenuOpen, setIsMoreMenuOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasActiveConversation = Boolean(activeConversationId);
  const isOverflowTabActive = OVERFLOW_TABS.some((tab) => tab.id === activeTab);
  const titleCompanyIdHint = companyIdFromConversationTitle(activeCompanyIdHint) ?? companyIdFromConversationTitle(activeConversationTitle);
  const normalizedActiveCompanyIdHint = (
    titleCompanyIdHint
    ?? companyIdFromHint(activeCompanyIdHint)
  );

  const effectiveCompanies = useMemo(() => resolveEffectiveCompanies({
    activeConversationId,
    activeCompanyIdHint: normalizedActiveCompanyIdHint,
    activeCompany: company,
    companies,
  }), [activeConversationId, companies, company, normalizedActiveCompanyIdHint]);

  const loadCompany = useCallback(async (requestedCompanyId?: string | null, requestedChannelId?: string | null) => {
    setBusy(true);
    setError(null);
    try {
      const requestedCompanyWasProvided = requestedCompanyId !== undefined;
      const hintedCompanyId = requestedCompanyWasProvided
        ? companyIdFromHint(requestedCompanyId)
        : normalizedActiveCompanyIdHint;
      const activeCompanyCandidate = requestedCompanyWasProvided ? null : activeCompanyId;

      const statusTarget = hintedCompanyId
        ? hintedCompanyId
        : activeConversationId
          ? { conversationId: activeConversationId, bootstrap: true }
          : activeCompanyCandidate ?? null;
      const statusRequest = statusTarget
        ? companyResources.getCompanyStatus(statusTarget)
        : Promise.resolve({ bootstrapped: false, company_id: "", company: null });
      const [companyListResult, statusResult, p2pStatusResult, p2pIdentityResult, peersResult] = await Promise.allSettled([
        companyResources.listCompanies(),
        statusRequest,
        companyResources.getP2PStatus(),
        companyResources.getP2PIdentity(),
        companyResources.listP2PPeers(),
      ]);

      const listedCompanies = companyListResult.status === "fulfilled" ? companyListResult.value.companies : [];
      let statusCompany = statusResult.status === "fulfilled" ? statusResult.value.company ?? null : null;
      const selectedId = resolveSelectedCompanyId({
        activeConversationId,
        activeCompanyId: activeCompanyCandidate,
        hintedCompanyId,
        statusCompany,
        companies: listedCompanies,
      });
      if (statusCompany?.id && statusCompany.id !== selectedId) {
        statusCompany = null;
      }
      if (!statusCompany && selectedId) {
        statusCompany = listedCompanies.find((item) => item.id === selectedId) ?? null;
      }
      setCompanies(listedCompanies);
      setActiveCompanyId(selectedId);
      setCompany(statusCompany);

      if (p2pStatusResult.status === "fulfilled") setP2PStatus(p2pStatusResult.value);
      if (p2pIdentityResult.status === "fulfilled") setP2PIdentity(p2pIdentityResult.value.identity);
      if (peersResult.status === "fulfilled") setPeers(peersResult.value.peers);

      const loadErrors = [
        settledErrorMessage("Company list", companyListResult),
        settledErrorMessage("Company status", statusResult),
      ].filter((message): message is string => Boolean(message));

      if (selectedId) {
        const [agentResult, channelResult, taskResult, routeResult, runResult] = await Promise.allSettled([
          companyResources.listCompanyAgents(selectedId),
          companyResources.listCompanyChannels(selectedId),
          companyResources.listCompanyTasks(selectedId),
          companyResources.listCompanyInboundRoutes(selectedId),
          companyResources.listCompanyRuns(selectedId, { limit: 80 }),
        ]);
        const nextAgents = agentResult.status === "fulfilled" ? agentResult.value.agents : arrayFromRecord(statusCompany?.agents);
        setAgents(nextAgents);
        const nextChannels = channelResult.status === "fulfilled" ? channelResult.value.channels : arrayFromRecord(statusCompany?.channels);
        setChannels(nextChannels);
        const resolvedChannelId = resolveActiveChannelId(requestedChannelId ?? activeChannelId, nextChannels);
        setActiveChannelId(resolvedChannelId);
        setTasks(taskResult.status === "fulfilled" ? taskResult.value.tasks : arrayFromRecord(statusCompany?.tasks));
        setRoutes(routeResult.status === "fulfilled" ? routeResult.value.routes : arrayFromRecord(statusCompany?.inbound_routes));
        const [messageResult] = await Promise.allSettled([
          companyResources.listCompanyMessages(selectedId, resolveCompanyMessageListOptions(nextChannels, resolvedChannelId)),
        ]);
        setMessages(messageResult.status === "fulfilled" ? messageResult.value.messages : arrayFromRecord(statusCompany?.messages));
        setRuns(runResult.status === "fulfilled" ? runResult.value.runs : []);
        const channelError = settledErrorMessage("Channels", channelResult);
        const messageError = settledErrorMessage("Messages", messageResult);
        if (channelError) loadErrors.push(channelError);
        if (messageError) loadErrors.push(messageError);
        const inboxResults = await Promise.allSettled(
          nextAgents.map((agent) => companyResources.listCompanyAgentInbox(selectedId, agent.agent_id, { limit: 20 })),
        );
        setInboxItems(
          inboxResults.flatMap((result) => result.status === "fulfilled" ? result.value.inbox : []),
        );
      } else {
        setAgents([]);
        setChannels([]);
        setTasks([]);
        setRuns([]);
        setInboxItems([]);
        setRoutes([]);
        setMessages([]);
      }

      if (loadErrors.length > 0) {
        setError(loadErrors.join(" "));
      }
    } finally {
      setBusy(false);
    }
  }, [activeChannelId, activeCompanyId, activeConversationId, normalizedActiveCompanyIdHint]);

  useEffect(() => {
    setActiveCompanyId(normalizedActiveCompanyIdHint);
    void loadCompany(normalizedActiveCompanyIdHint);
  }, [activeConversationId, normalizedActiveCompanyIdHint]);

  useEffect(() => {
    if (!titleCompanyIdHint || activeCompanyId === titleCompanyIdHint) return;
    setActiveCompanyId(titleCompanyIdHint);
    void loadCompany(titleCompanyIdHint);
  }, [activeCompanyId, loadCompany, titleCompanyIdHint]);

  useEffect(() => {
    if (!activeCompanyId) return undefined;
    const intervalId = window.setInterval(() => {
      void loadCompany(activeCompanyId);
    }, 30000);
    return () => window.clearInterval(intervalId);
  }, [activeCompanyId, loadCompany]);

  const activeCompany = company ?? effectiveCompanies.find((item) => item.id === activeCompanyId) ?? null;

  const run = async (work: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await work();
      await loadCompany(activeCompanyId);
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Company action failed.");
    } finally {
      setBusy(false);
    }
  };

  const selectTab = (tabId: CompanyTab) => {
    setActiveTab(tabId);
    setIsMoreMenuOpen(false);
  };

  const renderTab = () => {
    if (!activeCompanyId && activeTab !== "p2p") {
      return <div className="p-3 text-[12px] text-zinc-500">Start or send a chat message to create its employee group.</div>;
    }
    switch (activeTab) {
      case "channels":
        return (
          <CompanyChannelView
            channels={channels}
            messages={messages}
            activeChannelId={activeChannelId}
            busy={busy}
            onChannelChange={(channelId) => {
              if (!activeCompanyId) return;
              setActiveChannelId(channelId);
              void loadCompany(activeCompanyId, channelId);
            }}
            onSendMessage={(content, channelId) => activeCompanyId && void run(() => companyResources.sendCompanyMessage(activeCompanyId, { content, channel_id: channelId, sender_id: "user" }))}
          />
        );
      case "agents":
        return (
          <CompanyAgentList
            agents={agents}
            runs={runs}
            inboxItems={inboxItems}
            busy={busy}
            onUpsertAgent={(agent) => activeCompanyId && void run(() => companyResources.upsertCompanyAgent(activeCompanyId, agent))}
          />
        );
      case "routes":
        return (
          <CompanyInboundRoutesPanel
            routes={routes}
            busy={busy}
            onUpsertRoute={(route) => activeCompanyId && void run(() => companyResources.upsertCompanyInboundRoute(activeCompanyId, route))}
            onDeleteRoute={(routeId) => activeCompanyId && void run(() => companyResources.deleteCompanyInboundRoute(activeCompanyId, routeId))}
          />
        );
      case "settings":
        return (
          <CompanySettingsPanel
            settings={activeCompany?.settings ?? {}}
            busy={busy}
            onSave={(settings) => activeCompanyId && void run(() => companyResources.updateCompanySettings(activeCompanyId, settings))}
          />
        );
      case "p2p":
        return (
          <CompanyP2PPanel
            status={p2pStatus}
            identity={p2pIdentity}
            peers={peers}
            busy={busy}
            onStartPairing={(peerLabel) => void run(() => companyResources.startP2PPairing({ peer_label: peerLabel, allowed_company_ids: activeCompanyId ? [activeCompanyId] : undefined }))}
            onSendMessage={(peerId, text) => void run(() => companyResources.sendP2PMessage(peerId, { text, body: { text, company_id: activeCompanyId ?? undefined } }))}
          />
        );
      case "tasks":
      default:
        return (
          <CompanyTaskBoard
            tasks={tasks}
            agents={agents}
            runs={runs}
            busy={busy}
            onCreateTask={(title, targetAgentIds) => activeCompanyId && void run(() => companyResources.createCompanyTask(activeCompanyId, {
              title,
              target_agent_ids: targetAgentIds,
              source: "president",
              metadata: {
                ...(activeConversationId ? { conversation_id: activeConversationId } : {}),
                ...(activeConversationTitle ? { source_chat_title: activeConversationTitle } : {}),
                source_message: title,
              },
            }))}
            onCreateResearchTask={(query, targetAgentIds) => activeCompanyId && void run(async () => {
              const searchResult = await companyResources.webSearch(query, true);
              const sources = researchSources(searchResult.sources);
              return companyResources.createCompanyTask(activeCompanyId, {
                title: `Deep research: ${query}`,
                description: researchTaskDescription(query, sources),
                target_agent_ids: targetAgentIds.length > 0 ? targetAgentIds : ["research_specialist"],
                source: "president_deep_research",
                metadata: {
                  ...(activeConversationId ? { conversation_id: activeConversationId } : {}),
                  ...(activeConversationTitle ? { source_chat_title: activeConversationTitle } : {}),
                  source_message: query,
                  research_query: query,
                  search_provider: textValue(searchResult.provider) || "external_web",
                  sources,
                },
              });
            })}
            onUpdateTask={(taskId, updates) => activeCompanyId && void run(() => companyResources.updateCompanyTask(activeCompanyId, taskId, updates))}
            onDispatchTask={(taskId) => activeCompanyId && void run(() => companyResources.dispatchCompanyTask(activeCompanyId, taskId))}
          />
        );
    }
  };

  return (
    <div className="relative flex h-full min-h-0 flex-col bg-[#0a0a0c] text-zinc-300">
      <div className="border-b border-zinc-800/60 px-3 py-2">
        <p className="truncate text-[13px] font-medium text-zinc-100">Employees</p>
        <p className="truncate text-[10px] text-zinc-600">
          {activeConversationTitle || activeConversationId || activeCompany?.name || "start a chat to create employees"}
        </p>
      </div>

      {error && (
        <div className="m-2 flex items-start gap-2 rounded-md border border-amber-500/20 bg-amber-500/10 px-2 py-1.5 text-[11px] text-amber-200">
          <AlertTriangle size={13} className="mt-0.5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <CompanyTree
        companies={effectiveCompanies}
        activeCompanyId={activeCompanyId}
        busy={busy}
        emptyMessage={hasActiveConversation ? "No employee group loaded." : "Start or send a chat message to create its employee group."}
        onSelect={(companyId) => void loadCompany(companyId)}
        onBootstrap={hasActiveConversation ? () => void run(() => companyResources.bootstrapCompanyWorkspace(
          {
            source: "webapp",
            name: "Executive Team",
            ...(activeConversationId ? { conversation_id: activeConversationId, scope: "conversation" } : {}),
          },
          activeConversationId ? { conversationId: activeConversationId, scope: "conversation" } : undefined,
        )) : undefined}
        onRefresh={() => void loadCompany(activeCompanyId)}
      />

      <div className="grid grid-cols-3 gap-1 border-b border-zinc-800/60 p-2">
        {PRIMARY_TABS.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => selectTab(tab.id)}
              className={`flex h-7 min-w-0 items-center justify-center gap-1.5 rounded-md px-2 text-[11px] transition-colors ${
                activeTab === tab.id ? "bg-zinc-800 text-zinc-100" : "text-zinc-500 hover:bg-zinc-900 hover:text-zinc-300"
              }`}
            >
              <Icon size={12} className="shrink-0" />
              <span className="truncate">{tab.label}</span>
            </button>
          );
        })}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto pb-14">
        {renderTab()}
      </div>

      {isMoreMenuOpen && (
        <button
          type="button"
          aria-label="Close employee workspace options"
          className="fixed inset-0 rumi-layer-panel cursor-default bg-transparent"
          onClick={() => setIsMoreMenuOpen(false)}
        />
      )}
      <div className="absolute bottom-3 right-3 rumi-layer-local-popover flex flex-col items-end gap-2">
        {isMoreMenuOpen && (
          <div role="menu" className="w-44 overflow-hidden rounded-xl border border-zinc-700/70 bg-zinc-950 py-1 shadow-2xl">
            {OVERFLOW_TABS.map((tab) => {
              const Icon = tab.icon;
              const selected = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  role="menuitem"
                  onClick={() => selectTab(tab.id)}
                  className={`flex w-full items-center gap-2 px-3 py-2 text-left text-[12px] transition-colors ${
                    selected ? "bg-zinc-800 text-zinc-100" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100"
                  }`}
                >
                  <Icon size={13} className="shrink-0" />
                  <span className="truncate">{tab.label}</span>
                </button>
              );
            })}
          </div>
        )}
        <button
          type="button"
          aria-label="Employee workspace options"
          aria-haspopup="menu"
          aria-expanded={isMoreMenuOpen}
          onClick={() => setIsMoreMenuOpen((open) => !open)}
          className={`flex h-9 w-9 items-center justify-center rounded-full border shadow-xl transition-colors ${
            isMoreMenuOpen || isOverflowTabActive
              ? "border-zinc-600 bg-zinc-100 text-zinc-950"
              : "border-zinc-800 bg-zinc-950 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100"
          }`}
          title="Employee workspace options"
        >
          <Settings size={16} />
        </button>
      </div>
    </div>
  );
}
