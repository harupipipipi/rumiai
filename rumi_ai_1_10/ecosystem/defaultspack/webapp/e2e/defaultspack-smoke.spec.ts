import { expect, test, type Page, type Route } from "@playwright/test";

test.use({ viewport: { width: 1440, height: 900 } });

const now = 1_785_000_000_000;
const historyChatDropMime = "application/rumi-history-chat";

function ok(data: unknown) {
  return { status: "ok", data };
}

function smokeConversation() {
  return {
    id: "c-smoke",
    title: "Preview Calendar Chat",
    created_at: now - 60_000,
    updated_at: now,
    model: "stub/default",
    tags: ["coding"],
    is_starred: false,
    is_pinned: false,
    is_archived: false,
    messages: [
      {
        id: "m-user",
        role: "user",
        content: [{ type: "text", text: "Show the current tool state." }],
        raw_text: "Show the current tool state.",
        created_at: now - 20_000,
        conversation_id: "c-smoke",
        parent_id: null,
        children_ids: [],
        sequence_number: 1,
        finish_reason: null,
        usage: null,
        widget: null,
      },
      {
        id: "m-assistant",
        role: "assistant",
        content: [{ type: "text", text: "Preview smoke response with tool timeline." }],
        raw_text: "Preview smoke response with tool timeline.",
        created_at: now - 10_000,
        conversation_id: "c-smoke",
        parent_id: "m-user",
        children_ids: [],
        sequence_number: 2,
        finish_reason: "stop",
        usage: { total_tokens: 42 },
        widget: null,
        model: "stub/default",
        metadata: {
          timing: {
            thinking_started_at: now - 15_000,
            completed_at: now - 10_000,
          },
        },
        events: [
          {
            type: "tool_call_started",
            phase: "tool_call_started",
            tool_call_id: "call-files",
            tool_name: "coding_file_list",
            arguments: { path: "src" },
            timestamp: now - 14_000,
          },
          {
            type: "tool_call_completed",
            phase: "tool_call_completed",
            tool_call_id: "call-files",
            tool_name: "coding_file_list",
            arguments: { path: "src" },
            display_text: "Listed 2 files",
            next_step: "Ready for implementation",
            timestamp: now - 11_000,
          },
        ],
        tool_logs: [
          {
            tool_name: "web_search",
            tool_call_id: "call-web",
            arguments: { query: "defaultspack smoke" },
            result: { status: "ok", data: { summary: "1 result" } },
            timestamp: now - 9_000,
          },
        ],
      },
    ],
  };
}

const smokeProfile = {
  profile_id: "stub/default",
  qualified_model_id: "stub/default",
  provider_id: "stub",
  provider_display_name: "Stub",
  model_id: "default",
  display_name: "Stub Default",
  max_context: -1,
  max_context_tokens: -1,
  supports_thinking: false,
  supports_tool_calling: true,
  supports_vision: false,
  local: true,
  availability: { local: true, configured: true },
};

const sidebarItems = [
  {
    id: "web_search",
    label: "Web Search",
    category: "tool",
    description: "Search the web from the composer.",
    tags: ["research"],
    risk: "medium",
    ui: {
      group_id: "research",
      group_label: "Research",
      group_icon: "search",
      item_icon: "web_search",
      widget_kind: "tool_toggle",
      drop_capabilities: ["composer.toggle_chip"],
      composer_label: "Web Search",
      composer_description: "Search the web.",
    },
    panel: {
      kind: "tool",
      title: "Web Search",
      notes: ["Mocked for Playwright smoke coverage."],
    },
  },
  {
    id: "scheduler",
    label: "Scheduler",
    category: "system",
    description: "Schedule and trigger controls.",
    ui: { item_icon: "calendar" },
    panel: {
      kind: "actions",
      title: "Scheduler",
      notes: ["Calendar and trigger smoke surface."],
      actions: [
        {
          id: "schedules.list",
          label: "Calendar",
          icon: "schedules",
          method: "GET",
        },
      ],
    },
  },
];

const settingsValues = {
  general: {
    language: "en",
    composer_placeholder: "Message Rumi...",
    keyboard_button_navigation: true,
    show_activity_in_messages: true,
  },
  models: {
    preferred_model: "stub/default",
    favorite_profiles: ["stub/default"],
  },
  preview: {
    max_items: 12,
    auto_open: false,
    default_mode: "auto",
  },
  chat_rendering: {
    unknown_block_strategy: "hidden",
    show_widgets: true,
  },
  sidebar: {
    pinned_item_ids: ["web_search"],
    starred_item_ids: [],
    custom_tool_tags: {},
  },
  tools: {},
  commands: {},
};

async function fulfill(route: Route, data: unknown) {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(ok(data)),
  });
}

async function installDefaultspackApiMocks(page: Page) {
  await page.addInitScript(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const conversation = smokeConversation();

    if (path === "/api/health") {
      return fulfill(route, { status: "ok", pack: "defaultspack", ts: "2026-05-20T00:00:00Z" });
    }

    if (path === "/api/ui/catalog") {
      return fulfill(route, {
        app: { id: "defaultspack", name: "Rumi", account: { display_name: "Smoke User", plan_label: "Local" } },
        agent_service: { profiles: [], capabilities: [], presets: [] },
        sidebar: {
          filters: [
            { id: "all", label: "All" },
            { id: "tool", label: "Tools" },
            { id: "system", label: "System" },
          ],
          items: sidebarItems,
        },
        settings: { sections: [], values: settingsValues },
        chat_rendering: { renderers: [] },
        extension_points: [],
      });
    }

    if (path === "/api/ui/settings") {
      return fulfill(route, { sections: [], values: settingsValues });
    }

    if (path === "/api/ui/commands") {
      return fulfill(route, { commands: [] });
    }

    if (path === "/api/ai/profiles") {
      return fulfill(route, { profiles: [smokeProfile], count: 1 });
    }

    if (path === "/api/chat/conversations" && method === "GET") {
      return fulfill(route, { conversations: [{ ...conversation, messages: [] }], total: 1 });
    }

    if (path === "/api/chat/conversations" && method === "POST") {
      return fulfill(route, conversation);
    }

    if (path === "/api/chat/conversations/c-smoke") {
      return fulfill(route, conversation);
    }

    if (path === "/api/ui/conversations/c-smoke/preview") {
      return fulfill(route, {
        conversation_id: "c-smoke",
        previews: [
          {
            id: "preview-calendar",
            toolStepId: "call-files",
            timestamp: now - 8_000,
            data: {
              type: "file",
              filename: "calendar-smoke.json",
              size: "tool artifact",
              content: '{ "job": "nightly-review", "status": "ready" }',
            },
          },
        ],
        summary: { file: 1 },
      });
    }

    if (path === "/api/chat/steer") {
      return fulfill(route, { items: [] });
    }

    if (path === "/api/agent/schedules") {
      return fulfill(route, {
        schedules: [
          { id: "nightly-review", name: "nightly-review", schedule: "every 1h", next_run_at: "2026-05-20T12:00:00Z" },
        ],
      });
    }

    if (path === "/api/coding/workspaces") {
      return fulfill(route, {
        workspaces: [{ workspace_id: "ws-main", label: "Main Repo", root_path: "/repo", trusted: true }],
        selected_workspace_id: "ws-main",
      });
    }

    if (path === "/api/coding/context") {
      return fulfill(route, {
        branch: "main",
        root_folder: "/repo",
        workspace_id: "ws-main",
        workspace_root: "/repo",
        directory: ".",
        files: ["src/App.tsx", "README.md"],
        entries: [
          { name: "src", path: "src", is_dir: true, size: 0 },
          { name: "README.md", path: "README.md", is_dir: false, size: 200 },
        ],
        git: { branch: "main", clean: false, modified: ["src/App.tsx"], untracked: [], staged: [] },
      });
    }

    if (path === "/api/coding/git/branch") {
      return fulfill(route, { branch: "main", branches: ["main", "codex/pr97"], workspace_id: "ws-main" });
    }

    if (path === "/api/coding/git/status") {
      return fulfill(route, { branch: "main", clean: false, modified: ["src/App.tsx"], untracked: [], staged: [] });
    }

    if (path === "/api/coding/git/diff") {
      return fulfill(route, { diff: "-old\n+new", files_changed: 1, files: ["src/App.tsx"], workspace_id: "ws-main" });
    }

    if (path === "/api/coding/approvals") {
      return fulfill(route, { requests: [], pending: [], count: 0 });
    }

    if (path === "/api/coding/checkpoints") {
      return fulfill(route, { checkpoints: [], workspace_id: "ws-main", workspace_root: "/repo" });
    }

    if (path === "/api/browser/artifacts") {
      return fulfill(route, {
        artifacts: [{ artifact_id: "browser-1", session_id: "s1", action: "browser.session", created_at: "2026-05-20T00:00:00Z", url: "https://example.com" }],
        count: 1,
      });
    }

    if (path === "/api/tools/mcp") {
      return fulfill(route, {
        servers: [{ server_id: "filesystem", name: "Filesystem MCP", transport: "stdio", connected: true, permissions: { approved: true } }],
        count: 1,
      });
    }

    return fulfill(route, {});
  });
}

async function openDefaultspack(page: Page, path = "/chat") {
  await installDefaultspackApiMocks(page);
  await page.goto(path);
  await expect(page.getByText("Preview Calendar Chat").first()).toBeVisible();
}

test("preview pane opens from the chat canvas peek", async ({ page }) => {
  await openDefaultspack(page);

  await page.getByTitle("Canvas を開く").click();

  const preview = page.getByLabel("Activity preview");
  await expect(preview).toBeVisible();
  await expect(preview).toContainText("calendar-smoke.json");
});

test("calendar action renders a scheduler preview", async ({ page }) => {
  await openDefaultspack(page);

  await page.getByTitle("Scheduler").click();
  await expect(page.getByText("Calendar and trigger smoke surface.")).toBeVisible();
  await page.locator('button[title="Calendar"]').last().click();

  const preview = page.getByLabel("Activity preview");
  await expect(preview).toContainText("Calendar.json");
  await expect(preview).toContainText("nightly-review");
});

test("history chat dnd accepts a real chat reference drop into the composer", async ({ page }) => {
  await openDefaultspack(page);

  await expect(page.getByText("Preview Calendar Chat").first()).toBeVisible();
  const composer = page.locator(".rumi-composer-frame");
  await expect(composer).toBeVisible();
  const dataTransfer = await page.evaluateHandle((mime) => {
    const dataTransfer = new DataTransfer();
    dataTransfer.setData(
      mime,
      JSON.stringify({
        conversationId: "c-smoke",
        title: "Preview Calendar Chat",
        conversationKind: "coding",
        tags: ["coding"],
      }),
    );
    return dataTransfer;
  }, historyChatDropMime);
  await composer.dispatchEvent("dragover", { dataTransfer });
  await composer.dispatchEvent("drop", { dataTransfer });
  await dataTransfer.dispose();

  await expect(page.locator(".rumi-composer-frame")).toContainText("Preview Calendar Chat");
});

test("tool timeline shows streamed activity details", async ({ page }) => {
  await openDefaultspack(page);

  const timeline = page.locator(".rumi-tool-activity");
  await expect(timeline).toBeVisible();
  await expect(timeline).toContainText("ファイル");
  await expect(timeline).toContainText("src");
  await expect(timeline).toContainText("Listed 2 files");
});

test("mcp cockpit UI lists connected MCP servers", async ({ page }) => {
  await openDefaultspack(page, "/coding");

  await expect(page.getByLabel("Coding cockpit")).toBeVisible();
  const mcpServers = page.getByLabel("MCP servers");
  await expect(mcpServers).toContainText("Filesystem MCP");
  await expect(mcpServers).toContainText("approved");
});
