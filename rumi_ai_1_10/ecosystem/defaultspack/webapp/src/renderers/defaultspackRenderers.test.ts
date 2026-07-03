import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { CompanyAgentList } from "../components/company/CompanyAgentList";
import { CompanyTaskBoard } from "../components/company/CompanyTaskBoard";
import { CompanyWorkspacePanel } from "../components/company/CompanyWorkspacePanel";
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

test("chat header renders active agent status chips", () => {
  const html = renderToStaticMarkup(
    createElement(defaultspackRenderers.chatHeader, {
      title: "Feature Chat",
      showPreview: false,
      canShowPreview: false,
      canOpenSettings: true,
      agentLabel: "Mini Coding Agent Profile",
      agentSurface: "mode_agent",
      activationReason: "manual_profile_switch",
      reviewGateApproved: false,
      onTogglePreview: () => {},
      onOpenSettings: () => {},
    }),
  );

  assert.match(html, /Feature Chat/);
  assert.match(html, /Mode Agent: Mini Coding Agent Profile/);
  assert.match(html, /Review gate pending/);
  assert.match(html, /manual profile switch/);
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
                content: "Run a real MiniMax task through the Workroom.",
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
  assert.match(html, /Workroom Conversation/);
  assert.match(html, /Deep research with DuckDuckGo/);
  assert.match(html, /Run a real MiniMax task through the Workroom/);
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

  assert.match(html, /Workroom/);
  assert.doesNotMatch(html, /Employee Group/);
  assert.match(html, /Workroom options/);
  assert.doesNotMatch(html, />Routes</);
  assert.doesNotMatch(html, />P2P</);
  assert.match(html, /Start or send a chat message to create its workroom/);
  assert.match(html, /Registered Profiles/);
  assert.doesNotMatch(html, /Rumi Operations Company/);
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
  assert.match(html, /Workroom Conversation/);
  assert.match(html, /Try the same task with stub\/default/);
  assert.match(html, /stub: provider is not configured/);
});
