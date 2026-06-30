import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { CompanyAgentList } from "../components/company/CompanyAgentList";
import { CompanyChannelView } from "../components/company/CompanyChannelView";
import { CompanyTaskBoard } from "../components/company/CompanyTaskBoard";
import { CompanyTree } from "../components/company/CompanyTree";
import {
  CompanyWorkspacePanel,
  MIMO_CODING_COMPANY_ID,
  resolveActiveChannelId,
  resolveCompanyMessageListOptions,
  resolveCompanyWorkspaceHint,
  resolveCompanyWorkspaceHintFromGroup,
  resolveEffectiveCompanies,
  resolveSelectedCompanyId,
} from "../components/company/CompanyWorkspacePanel";
import { buildCompactHistoryRailItems, buildGroupsFromChats } from "../components/HistoryBoard";
import { defaultspackRendererIds, defaultspackRenderers, resolveDefaultspackRenderers } from "./defaultspackRenderers";

test("defaultspack renderer registry covers visible shell regions", () => {
  assert.deepEqual([...defaultspackRendererIds].sort(), [
    "activity_preview",
    "chat_header",
    "chat_messages",
    "composer",
    "history",
    "right_sidebar",
    "settings_modal",
    "title_bar",
  ]);
});

test("defaultspack renderer registry exposes render modules", () => {
  assert.equal(typeof defaultspackRenderers.titleBar, "function");
  assert.equal(typeof defaultspackRenderers.historyBoard, "function");
  assert.equal(typeof defaultspackRenderers.chatHeader, "function");
  assert.equal(typeof defaultspackRenderers.chatMessages, "function");
  assert.equal(typeof defaultspackRenderers.composer, "function");
  assert.equal(typeof defaultspackRenderers.toolPreviewPanel, "function");
  assert.equal(typeof defaultspackRenderers.rightSidebar, "function");
  assert.equal(typeof defaultspackRenderers.settingsModal, "function");
});

test("defaultspack renderer resolver keeps builtin fallback for untrusted modules", () => {
  const resolved = resolveDefaultspackRenderers({
    shell: {
      layout: {
        id: "test",
        regions: [
          { id: "composer", renderer: "custom_composer", enabled: true },
        ],
      },
      renderers: [
        {
          id: "custom_composer",
          component: "CustomComposer",
          module: "https://example.com/composer.js",
          trust: "local",
        },
      ],
    },
    sidebar: { filters: [], items: [] },
    settings: { sections: [], values: {} },
    chat_rendering: { renderers: [] },
    extension_points: [],
  });

  assert.equal(resolved.composer, defaultspackRenderers.composer);
});

test("company agent list renders operational role details", () => {
  const html = renderToStaticMarkup(
    createElement(CompanyAgentList, {
      agents: [
        {
          agent_id: "reviewer",
          display_name: "Reviewer",
          role_key: "reviewer",
          model: "stub/default",
          allowed_tools: ["coding_git_diff"],
          aliases: ["review"],
        },
      ],
    }),
  );

  assert.match(html, /Reviewer/);
  assert.match(html, /@review/);
});

test("company task board renders dispatched completed runs", () => {
  const html = renderToStaticMarkup(
    createElement(CompanyTaskBoard, {
      agents: [{ agent_id: "minimax_worker", role_key: "minimax_worker" }],
      tasks: [
        {
          id: "task-1",
          company_id: "operations-company",
          title: "Live MiniMax smoke",
          target_agent_ids: ["minimax_worker"],
          status: "completed",
        },
      ],
      runs: [
        {
          link_id: "link-1",
          company_id: "operations-company",
          task_id: "task-1",
          agent_id: "minimax_worker",
          run_id: "agent-1",
          status: "completed",
          agent_run: {
            status: "completed",
            model: "stub/default",
            result_preview: "Visible MiniMax result",
            conversation: [
              {
                role: "user",
                label: "Assignment",
                content: "Run a real MiniMax task through Company Workspace.",
              },
              {
                role: "assistant",
                label: "Agent reply",
                content: "Visible MiniMax result",
              },
            ],
          },
        },
      ],
      onCreateTask: () => {},
      onDispatchTask: () => {},
      onCreateResearchTask: () => {},
    }),
  );

  assert.match(html, /Live MiniMax smoke/);
  assert.match(html, /minimax_worker/);
  assert.match(html, /completed/);
  assert.match(html, /stub\/default/);
  assert.match(html, /Employee Conversation/);
  assert.match(html, /Deep research with DuckDuckGo/);
  assert.match(html, /Run a real MiniMax task through Company Workspace/);
  assert.match(html, /Agent reply/);
  assert.match(html, /Visible MiniMax result/);
});

test("company workspace renders a visible empty state before a chat exists", () => {
  const html = renderToStaticMarkup(
    createElement(CompanyWorkspacePanel, {
      activeConversationId: null,
      activeConversationTitle: "New Conversation",
    }),
  );

  assert.match(html, /Employees/);
  assert.match(html, /Employee Group/);
  assert.match(html, /Employee workspace options/);
  assert.doesNotMatch(html, />Routes</);
  assert.doesNotMatch(html, />P2P</);
  assert.match(html, /Start or send a chat message to create its employee group/);
  assert.doesNotMatch(html, /Rumi Operations Company/);
});

test("company workspace selects and renders the first global MiMo company without a chat or hint", () => {
  const companies = [
    {
      id: MIMO_CODING_COMPANY_ID,
      name: "MiMo Coding Company",
      agent_count: 7,
      task_count: 6,
    },
    {
      id: "operations-company",
      name: "Rumi Operations Company",
      agent_count: 9,
      task_count: 1,
    },
  ];
  const selectedId = resolveSelectedCompanyId({
    activeConversationId: null,
    activeCompanyId: null,
    hintedCompanyId: null,
    statusCompany: null,
    companies,
  });

  const html = renderToStaticMarkup(
    createElement(CompanyTree, {
      companies,
      activeCompanyId: selectedId,
    }),
  );

  assert.equal(selectedId, MIMO_CODING_COMPANY_ID);
  assert.match(html, /MiMo Coding Company/);
  assert.match(html, /7 employees/);
  assert.match(html, /6 tasks/);
  assert.doesNotMatch(html, /Start or send a chat message/);
});

test("company workspace keeps global companies visible for conversation-scoped groups", () => {
  const effectiveCompanies = resolveEffectiveCompanies({
    activeConversationId: "chat-1",
    activeCompanyIdHint: null,
    activeCompany: {
      id: "chat-team-1",
      name: "Executive Team",
      agent_count: 2,
      task_count: 0,
    },
    companies: [
      {
        id: "mimo-coding-company",
        name: "MiMo Coding Company",
        agent_count: 7,
        task_count: 6,
      },
      {
        id: "operations-company",
        name: "Rumi Operations Company",
        agent_count: 9,
        task_count: 0,
      },
    ],
  });

  assert.deepEqual(effectiveCompanies.map((company) => company.id), [
    "chat-team-1",
    "mimo-coding-company",
    "operations-company",
  ]);
});

test("company workspace resolves MiMo company hints from group and profile context", () => {
  assert.equal(resolveCompanyWorkspaceHint({
    groupId: "company:mimo-coding-company",
  }), "mimo-coding-company");
  assert.equal(resolveCompanyWorkspaceHint({
    groupId: "group-coding",
  }), null);
  assert.equal(resolveCompanyWorkspaceHint({
    conversationKind: "mimo_coding_company",
  }), "mimo-coding-company");
  assert.equal(resolveCompanyWorkspaceHint({
    profileId: "defaultspack.mimo_coding_company",
  }), "mimo-coding-company");
  assert.equal(resolveCompanyWorkspaceHint({
    tags: ["company", "mimo-coding-company"],
  }), "mimo-coding-company");
});

test("company workspace resolves selected history company groups", () => {
  assert.equal(resolveCompanyWorkspaceHintFromGroup({
    id: "custom-company-mimo-coding-company",
    sourceGroupId: "company:mimo-coding-company",
    chats: [],
    subGroups: [],
  }), "mimo-coding-company");
  assert.equal(resolveCompanyWorkspaceHintFromGroup({
    id: "group-company",
    chats: [{
      metadata: { group_id: "company:mimo-coding-company" },
      tags: [],
    }],
    subGroups: [],
  }), "mimo-coding-company");
  assert.equal(resolveCompanyWorkspaceHintFromGroup({
    id: "group-coding",
    chats: [],
    subGroups: [],
  }), null);
});

test("compact history company group keeps the selectable source group", () => {
  const groups = buildGroupsFromChats([
    {
      id: "mimo-company-chat",
      title: "MiMo coding company",
      date: "Today",
      type: "chat",
      metadata: {
        group_id: "company:mimo-coding-company",
        group_title: "company:mimo-coding-company",
      },
    },
  ]);
  const railGroup = buildCompactHistoryRailItems(groups)
    .find((item) => item.type === "group" && item.id === "company:mimo-coding-company");

  if (!railGroup || railGroup.type !== "group") {
    assert.fail("Expected compact rail to include the company group.");
  }
  assert.equal(resolveCompanyWorkspaceHintFromGroup(railGroup.group), "mimo-coding-company");
});

test("company workspace repairs stale channel selection when switching companies", () => {
  const channels = [
    { id: "ops-company" },
    { id: "qa-findings" },
  ];

  assert.equal(resolveActiveChannelId("qa-findings", channels), "qa-findings");
  assert.equal(resolveActiveChannelId("old-chat-channel", channels), "ops-company");
  assert.equal(resolveActiveChannelId(null, [{ id: "research" }]), "research");
});

test("company channels tab scopes and renders ops-company messages", () => {
  const channels = [
    { id: "ops-company", name: "Ops Company" },
    { id: "general", name: "General" },
  ];
  const resolvedChannelId = resolveActiveChannelId(null, channels);
  const messageOptions = resolveCompanyMessageListOptions(channels, resolvedChannelId);
  const html = renderToStaticMarkup(
    createElement(CompanyChannelView, {
      channels,
      activeChannelId: resolvedChannelId,
      messages: [
        {
          id: "message-ops",
          company_id: "operations-company",
          channel_id: "ops-company",
          sender_id: "ops_lead",
          content: "Ops handoff is visible",
        },
        {
          id: "message-general",
          company_id: "operations-company",
          channel_id: "general",
          sender_id: "pm",
          content: "General chatter hidden from ops channel",
        },
      ],
    }),
  );

  assert.equal(resolvedChannelId, "ops-company");
  assert.deepEqual(messageOptions, { limit: 80, tail: true, channel_id: "ops-company" });
  assert.match(html, /Ops handoff is visible/);
  assert.doesNotMatch(html, /General chatter hidden from ops channel/);
});

test("company task board renders agent run errors", () => {
  const html = renderToStaticMarkup(
    createElement(CompanyTaskBoard, {
      agents: [{ agent_id: "stub_worker", role_key: "stub_worker" }],
      tasks: [
        {
          id: "task-err",
          company_id: "operations-company",
          title: "Stub fallback smoke",
          target_agent_ids: ["stub_worker"],
          status: "blocked",
        },
      ],
      runs: [
        {
          link_id: "link-err",
          company_id: "operations-company",
          task_id: "task-err",
          agent_id: "stub_worker",
          run_id: "agent-err",
          status: "error",
          agent_run: {
            status: "error",
            model: "stub/default",
            error: "stub: provider is not configured",
            conversation: [
              {
                role: "user",
                label: "Assignment",
                content: "Try the same task with stub/default.",
              },
              {
                role: "error",
                label: "Agent error",
                content: "stub: provider is not configured",
                is_error: true,
              },
            ],
          },
        },
      ],
    }),
  );

  assert.match(html, /Stub fallback smoke/);
  assert.match(html, /stub\/default/);
  assert.match(html, /Try the same task with stub\/default/);
  assert.match(html, /Agent error/);
  assert.match(html, /stub: provider is not configured/);
});

test("company agent list renders latest agent run errors", () => {
  const html = renderToStaticMarkup(
    createElement(CompanyAgentList, {
      agents: [
        {
          agent_id: "stub_worker",
          display_name: "Stub Worker",
          role_key: "stub_worker",
          model: "stub/default",
          allowed_tools: [],
        },
      ],
      runs: [
        {
          link_id: "link-err",
          company_id: "operations-company",
          task_id: "task-err",
          agent_id: "stub_worker",
          run_id: "agent-err",
          status: "error",
          agent_run: {
            status: "error",
            model: "stub/default",
            error: "stub: provider is not configured",
            conversation: [
              {
                role: "user",
                label: "Assignment",
                content: "Try the same task with stub/default.",
              },
              {
                role: "error",
                label: "Agent error",
                content: "stub: provider is not configured",
                is_error: true,
              },
            ],
          },
        },
      ],
    }),
  );

  assert.match(html, /Stub Worker/);
  assert.match(html, /error/);
  assert.match(html, /Employee Conversation/);
  assert.match(html, /Try the same task with stub\/default/);
  assert.match(html, /stub: provider is not configured/);
});
