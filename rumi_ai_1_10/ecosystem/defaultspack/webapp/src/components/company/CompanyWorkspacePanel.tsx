import { AlertTriangle, Bot, ClipboardList, MessageSquare, Route, Settings, Share2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  AgentStudioConversationState,
  CompanyAgent,
  CompanyChannel,
  CompanyInboxItem,
  CompanyInboundRoute,
  CompanyMessage,
  CompanyRecord,
  CompanyRunLink,
  CompanyTask,
  Conversation,
  P2PIdentity,
  P2PPeer,
  P2PStatusResponse,
} from "../../lib/api";
import { arrayFromRecord, companyResources } from "../../features/company/resources/companyResources";
import { AgentStudioPanel } from "./AgentStudioPanel";
import { CompanyAgentList } from "./CompanyAgentList";
import { CompanyChannelView } from "./CompanyChannelView";
import { CompanyInboundRoutesPanel } from "./CompanyInboundRoutesPanel";
import { CompanyP2PPanel } from "./CompanyP2PPanel";
import { CompanySettingsPanel } from "./CompanySettingsPanel";
import { CompanyTaskBoard } from "./CompanyTaskBoard";
import { CompanyTree } from "./CompanyTree";

type CompanyTab = "tasks" | "channels" | "agents" | "profiles" | "teams" | "fusion" | "selection" | "routes" | "settings" | "p2p";

const TABS: Array<{ id: CompanyTab; label: string; icon: typeof ClipboardList }> = [
  { id: "tasks", label: "Tasks", icon: ClipboardList },
  { id: "channels", label: "Channels", icon: MessageSquare },
  { id: "agents", label: "Members", icon: Bot },
  { id: "profiles", label: "Profiles", icon: Bot },
  { id: "teams", label: "Teams", icon: Bot },
  { id: "fusion", label: "Fusion", icon: Bot },
  { id: "selection", label: "Selection", icon: ClipboardList },
  { id: "routes", label: "Routes", icon: Route },
  { id: "settings", label: "Settings", icon: Settings },
  { id: "p2p", label: "P2P", icon: Share2 },
];

const PRIMARY_TAB_IDS = new Set<CompanyTab>(["tasks", "channels", "agents"]);
const PRIMARY_TABS = TABS.filter((tab) => PRIMARY_TAB_IDS.has(tab.id));
const OVERFLOW_TABS = TABS.filter((tab) => !PRIMARY_TAB_IDS.has(tab.id));
const AGENT_STUDIO_TAB_IDS = new Set<CompanyTab>(["profiles", "teams", "fusion", "selection"]);

function textValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
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

export function CompanyWorkspacePanel({
  activeConversationId = null,
  activeConversationTitle = null,
  agentStudioState = null,
  onConversationUpdate,
}: {
  activeConversationId?: string | null;
  activeConversationTitle?: string | null;
  agentStudioState?: AgentStudioConversationState | null;
  onConversationUpdate?: (conversation: Conversation) => void;
}) {
  const [companies, setCompanies] = useState<CompanyRecord[]>([]);
  const [activeCompanyId, setActiveCompanyId] = useState<string | null>(null);
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
  const [activeTab, setActiveTab] = useState<CompanyTab>(activeConversationId ? "tasks" : "profiles");
  const [isMoreMenuOpen, setIsMoreMenuOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasActiveConversation = Boolean(activeConversationId);
  const isOverflowTabActive = OVERFLOW_TABS.some((tab) => tab.id === activeTab);

  const effectiveCompanies = useMemo(() => {
    if (activeConversationId) return company ? [company] : [];
    if (!company) return companies;
    return [company, ...companies.filter((item) => item.id !== company.id)];
  }, [activeConversationId, companies, company]);

  const loadCompany = useCallback(async (requestedCompanyId?: string | null) => {
    setBusy(true);
    setError(null);
    try {
      if (!requestedCompanyId && !activeConversationId) {
        setCompanies([]);
        setActiveCompanyId(null);
        setCompany(null);
        setAgents([]);
        setChannels([]);
        setTasks([]);
        setRuns([]);
        setInboxItems([]);
        setRoutes([]);
        setMessages([]);
        setP2PStatus(null);
        setP2PIdentity(null);
        setPeers([]);
        setActiveChannelId(null);
        return;
      }

      const statusTarget = requestedCompanyId
        ? requestedCompanyId
        : activeConversationId
          ? { conversationId: activeConversationId, bootstrap: true }
          : activeCompanyId ?? undefined;
      const [companyListResult, statusResult, p2pStatusResult, p2pIdentityResult, peersResult] = await Promise.allSettled([
        companyResources.listCompanies(),
        companyResources.getCompanyStatus(statusTarget),
        companyResources.getP2PStatus(),
        companyResources.getP2PIdentity(),
        companyResources.listP2PPeers(),
      ]);

      const listedCompanies = companyListResult.status === "fulfilled" ? companyListResult.value.companies : [];
      const statusCompany = statusResult.status === "fulfilled" ? statusResult.value.company ?? null : null;
      const selectedId = requestedCompanyId ?? statusCompany?.id ?? (activeConversationId ? null : activeCompanyId ?? listedCompanies[0]?.id ?? null);
      setCompanies(activeConversationId ? (statusCompany ? [statusCompany] : []) : listedCompanies);
      setActiveCompanyId(selectedId);
      setCompany(statusCompany);

      if (p2pStatusResult.status === "fulfilled") setP2PStatus(p2pStatusResult.value);
      if (p2pIdentityResult.status === "fulfilled") setP2PIdentity(p2pIdentityResult.value.identity);
      if (peersResult.status === "fulfilled") setPeers(peersResult.value.peers);

      if (selectedId) {
        const [agentResult, channelResult, taskResult, routeResult, messageResult, runResult] = await Promise.allSettled([
          companyResources.listCompanyAgents(selectedId),
          companyResources.listCompanyChannels(selectedId),
          companyResources.listCompanyTasks(selectedId),
          companyResources.listCompanyInboundRoutes(selectedId),
          companyResources.listCompanyMessages(selectedId, { limit: 80 }),
          companyResources.listCompanyRuns(selectedId, { limit: 80 }),
        ]);
        const nextAgents = agentResult.status === "fulfilled" ? agentResult.value.agents : arrayFromRecord(statusCompany?.agents);
        setAgents(nextAgents);
        const nextChannels = channelResult.status === "fulfilled" ? channelResult.value.channels : arrayFromRecord(statusCompany?.channels);
        setChannels(nextChannels);
        setActiveChannelId((current) => current ?? nextChannels[0]?.id ?? "ops-company");
        setTasks(taskResult.status === "fulfilled" ? taskResult.value.tasks : arrayFromRecord(statusCompany?.tasks));
        setRoutes(routeResult.status === "fulfilled" ? routeResult.value.routes : arrayFromRecord(statusCompany?.inbound_routes));
        setMessages(messageResult.status === "fulfilled" ? messageResult.value.messages : arrayFromRecord(statusCompany?.messages));
        setRuns(runResult.status === "fulfilled" ? runResult.value.runs : []);
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

      const firstError = [companyListResult, statusResult]
        .find((result) => result.status === "rejected") as PromiseRejectedResult | undefined;
      if (firstError) {
        setError(firstError.reason instanceof Error ? firstError.reason.message : "Company APIs are unavailable.");
      }
    } finally {
      setBusy(false);
    }
  }, [activeCompanyId, activeConversationId]);

  useEffect(() => {
    setActiveCompanyId(null);
    void loadCompany();
  }, [activeConversationId]);

  useEffect(() => {
    if (activeConversationId || activeCompanyId || activeTab !== "tasks") return;
    setActiveTab("profiles");
  }, [activeCompanyId, activeConversationId, activeTab]);

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
    if (!activeCompanyId && activeTab !== "p2p" && !AGENT_STUDIO_TAB_IDS.has(activeTab)) {
      return <div className="p-3 text-[12px] text-zinc-500">Start or send a chat message to create its workroom.</div>;
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
              setActiveChannelId(channelId);
              void loadCompany(activeCompanyId);
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
      case "profiles":
        return (
          <AgentStudioPanel
            section="profiles"
            conversationId={activeConversationId}
            conversationState={agentStudioState}
            onConversationUpdate={onConversationUpdate}
          />
        );
      case "teams":
        return (
          <AgentStudioPanel
            section="teams"
            conversationId={activeConversationId}
            conversationState={agentStudioState}
            onConversationUpdate={onConversationUpdate}
          />
        );
      case "fusion":
        return (
          <AgentStudioPanel
            section="fusion"
            conversationId={activeConversationId}
            conversationState={agentStudioState}
            onConversationUpdate={onConversationUpdate}
          />
        );
      case "selection":
        return (
          <AgentStudioPanel
            section="selection"
            conversationId={activeConversationId}
            conversationState={agentStudioState}
            onConversationUpdate={onConversationUpdate}
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
        <p className="truncate text-[13px] font-medium text-zinc-100">Workroom</p>
        <p className="truncate text-[10px] text-zinc-600">
          {activeConversationTitle || activeConversationId || activeCompany?.name || "start a chat to create a workroom"}
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
        emptyMessage={hasActiveConversation ? "No workroom loaded." : "Start or send a chat message to create its workroom."}
        onSelect={(companyId) => void loadCompany(companyId)}
        onBootstrap={hasActiveConversation ? () => void run(() => companyResources.bootstrapCompanyWorkspace(
          {
            source: "webapp",
            name: "Team Workroom",
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
          aria-label="Close workroom options"
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
          aria-label="Workroom options"
          aria-haspopup="menu"
          aria-expanded={isMoreMenuOpen}
          onClick={() => setIsMoreMenuOpen((open) => !open)}
          className={`flex h-9 w-9 items-center justify-center rounded-full border shadow-xl transition-colors ${
            isMoreMenuOpen || isOverflowTabActive
              ? "border-zinc-600 bg-zinc-100 text-zinc-950"
              : "border-zinc-800 bg-zinc-950 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100"
          }`}
          title="Workroom options"
        >
          <Settings size={16} />
        </button>
      </div>
    </div>
  );
}
