import { expect, test, type Page, type Route } from "@playwright/test";

test.use({ viewport: { width: 1440, height: 900 } });

// These specs exercise mocked UI contracts only. Live MCP proof is covered by
// the Python integration tests that assert tool_logs and tool_call events.
const now = 1_785_000_000_000;
const historyChatDropMime = "application/rumi-history-chat";

type ApiMockOptions = {
  onStreamRequest?: (payload: Record<string, unknown>) => void;
  streamEvents?: (message: Record<string, unknown>) => Record<string, unknown>[];
};

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
    conversation_kind: "coding",
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

const googleProfile = {
  profile_id: "google/gemini-2.5-flash",
  qualified_model_id: "google/gemini-2.5-flash",
  provider_id: "google",
  provider_display_name: "Google",
  model_id: "gemini-2.5-flash",
  display_name: "Gemini 2.5 Flash",
  max_context: 1_000_000,
  max_context_tokens: 1_000_000,
  supports_thinking: true,
  supports_tool_calling: true,
  supports_vision: true,
  local: false,
  availability: { configured: true },
};

const embeddingProfile = {
  profile_id: "google/text-embedding-004",
  qualified_model_id: "google/text-embedding-004",
  provider_id: "google",
  provider_display_name: "Google",
  model_id: "text-embedding-004",
  display_name: "Text Embedding 004",
  type: "embedding",
  max_context: 2048,
  max_context_tokens: 2048,
  supports_thinking: false,
  supports_tool_calling: false,
  supports_vision: false,
  local: false,
  configured: true,
  requires_api_key: false,
  capability_tags: ["embedding"],
  recommended_roles: ["tool_embedding"],
  availability: { configured: true },
};

const opencodeProfile = {
  profile_id: "opencode-go/qwen3.5-plus",
  qualified_model_id: "opencode-go/qwen3.5-plus",
  provider_id: "opencode-go",
  provider_display_name: "OpenCode Go",
  model_id: "qwen3.5-plus",
  display_name: "Qwen3.5 Plus via OpenCode Go",
  max_context: 128_000,
  max_context_tokens: 128_000,
  supports_thinking: false,
  supports_tool_calling: true,
  supports_vision: false,
  local: false,
  availability: { configured: true },
};

const opencodeZenProfile = {
  profile_id: "opencode-zen/mimo-v2.5-free",
  qualified_model_id: "opencode-zen/mimo-v2.5-free",
  provider_id: "opencode-zen",
  provider_display_name: "OpenCode Zen",
  model_id: "mimo-v2.5-free",
  display_name: "MiMo V2.5 Free via OpenCode Zen",
  max_context: 131_072,
  max_context_tokens: 131_072,
  supports_thinking: true,
  supports_tool_calling: false,
  supports_vision: false,
  local: false,
  availability: { configured: false, status: "requires_api_key" },
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
    id: "github_issue_search",
    label: "GitHub Issues",
    category: "tool",
    description: "Search GitHub issues and pull requests.",
    tags: ["github", "issues"],
    risk: "medium",
    ui: {
      group_id: "github",
      group_label: "GitHub",
      item_icon: "git",
      service_id: "github",
      widget_kind: "tool_toggle",
      drop_capabilities: ["composer.toggle_chip"],
      composer_label: "GitHub Issues",
      composer_description: "Search GitHub issues.",
    },
    panel: {
      kind: "tool",
      title: "GitHub Issues",
      notes: ["Mocked for service-level selection coverage."],
    },
  },
  {
    id: "scheduler",
    label: "Scheduler",
    category: "tool",
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

const catalogSkills = [
  {
    id: "feedback/live-review",
    label: "Live Review",
    description: "Require evidence-backed verification.",
    triggers: ["PR97_LIVE_REALITY_REVIEW"],
    applies_to_tools: ["web_search"],
    aliases: ["reality", "live-review"],
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
  calendar: {
    agent_current_chat: false,
    agent_model: "",
    agent_task_default: false,
    default_time: "09:00",
    quick_add_enabled: true,
    default_item_type: "task",
    week_start: "sunday",
    show_outside_days: true,
    show_time_picker: true,
    dim_weekends: true,
    task_color: "blue",
    time_slot_minutes: 15,
    event_color: "green",
    max_items_per_day: 3,
  },
  chat_rendering: {
    unknown_block_strategy: "hidden",
    show_widgets: true,
  },
  sidebar: {
    pinned_item_ids: ["web_search", "scheduler"],
    starred_item_ids: [],
    custom_tool_tags: {},
  },
  tools: {
    default_mode: "auto",
    selection_strategy: "hybrid",
    semantic_candidate_limit: 24,
    final_tool_limit: 8,
    catalog_ai_direct_limit: 80,
    selector_trace: "summary",
    standard_permissions: {
      read: "auto",
      search: "auto",
      create: "confirm",
      update: "confirm",
      send: "confirm",
      execute: "confirm",
      computer: "confirm",
      delete: "confirm",
    },
    service_permission_overrides: {},
    embedding_model: "",
  },
  commands: {},
};

const settingsSections = [
  {
    id: "tools",
    label: "機能と接続",
    description: "機能の選定、接続、実行時権限を管理します。",
    fields: [],
  },
  {
    id: "calendar",
    label: "カレンダー",
    description: "Calendar behavior.",
    fields: Array.from({ length: 14 }, (_, index) => ({
      id: `calendar_field_${index + 1}`,
      label: `Calendar Field ${index + 1}`,
      type: "text",
      default: "",
    })),
  },
];

const toolCatalogServices = [
  {
    service_id: "web",
    label: "Web検索",
    summary: "Web、検索、オンライン情報を扱います",
    connection_status: "connected",
    tool_count: 1,
    action_classes: ["search"],
  },
  {
    service_id: "github",
    label: "GitHub",
    summary: "リポジトリ、Issue、Pull Requestを扱います",
    connection_status: "connected",
    tool_count: 1,
    action_classes: ["search"],
  },
  {
    service_id: "calendar",
    label: "Calendar",
    summary: "予定やカレンダーを扱います",
    connection_status: "connected",
    tool_count: 1,
    action_classes: ["read"],
  },
];

const toolCatalogTools = [
  {
    tool_id: "web_search",
    service_id: "web",
    service_label: "Web検索",
    name: "Web Search",
    summary: "Search the web.",
    action_class: "search",
    risk: "medium",
    connection_status: "connected",
    minimum_permission: "auto",
    tags: ["research"],
  },
  {
    tool_id: "github_issue_search",
    service_id: "github",
    service_label: "GitHub",
    name: "GitHub Issues",
    summary: "Search GitHub issues and pull requests.",
    action_class: "search",
    risk: "medium",
    connection_status: "connected",
    minimum_permission: "auto",
    tags: ["github"],
  },
  {
    tool_id: "scheduler",
    service_id: "calendar",
    service_label: "Calendar",
    name: "Scheduler",
    summary: "Schedule and trigger controls.",
    action_class: "read",
    risk: "low",
    connection_status: "connected",
    minimum_permission: "auto",
    tags: ["calendar"],
  },
];

async function fulfill(route: Route, data: unknown) {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(ok(data)),
  });
}

async function fulfillStream(route: Route, message: Record<string, unknown>) {
  await route.fulfill({
    status: 200,
    contentType: "text/event-stream",
    body: [
      `data: ${JSON.stringify({ type: "message", message })}`,
      "",
      `data: ${JSON.stringify({ type: "done", message })}`,
      "",
    ].join("\n"),
  });
}

async function fulfillStreamEvents(route: Route, events: Record<string, unknown>[]) {
  await route.fulfill({
    status: 200,
    contentType: "text/event-stream",
    body: events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join(""),
  });
}

async function installDefaultspackApiMocks(page: Page, options: ApiMockOptions = {}) {
  await page.addInitScript(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  let currentSettingsValues = JSON.parse(JSON.stringify(settingsValues)) as typeof settingsValues;
  let conversationToolPreferences: Record<string, unknown> = {};
  const mcpServers = [
    { server_id: "filesystem", name: "Filesystem MCP", transport: "stdio", connected: true, permissions: { approved: true }, tools: ["mcp_fs_read_file"] },
  ];

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
        settings: { sections: settingsSections, values: currentSettingsValues },
        chat_rendering: { renderers: [] },
        skills: catalogSkills,
        extension_points: [],
      });
    }

    if (path === "/api/ui/settings" && method === "PUT") {
      const payload = request.postDataJSON() as { values?: typeof settingsValues };
      currentSettingsValues = JSON.parse(JSON.stringify(payload.values ?? currentSettingsValues));
      return fulfill(route, { sections: settingsSections, values: currentSettingsValues });
    }

    if (path === "/api/ui/settings") {
      return fulfill(route, { sections: settingsSections, values: currentSettingsValues });
    }

    if (path === "/api/ui/commands") {
      return fulfill(route, {
        commands: [
          {
            id: "coding",
            name: "coding",
            label: "Coding Mode",
            description: "Toggle coding mode.",
            category: "mode",
            visibility: "default",
            risk: "low",
            modes: ["chat", "coding", "agent"],
            execution: { type: "frontend", action: "set_mode_coding" },
          },
        ],
      });
    }

    if (path === "/api/ui/commands/execute" && method === "POST") {
      const payload = request.postDataJSON() as Record<string, unknown>;
      return fulfill(route, {
        executed: true,
        action: payload.command === "coding" ? "set_mode_coding" : "",
      });
    }

    if (path === "/api/ai/profiles") {
      return fulfill(route, { profiles: [smokeProfile, googleProfile, opencodeProfile, opencodeZenProfile], count: 4 });
    }

    if (path === "/api/ai/models/search" && method === "POST") {
      const payload = request.postDataJSON() as Record<string, unknown>;
      const types = Array.isArray(payload.type)
        ? payload.type.map((item) => String(item).trim())
        : [String(payload.type ?? "").trim()];
      const models = types.includes("embedding")
        ? [embeddingProfile]
        : [smokeProfile, googleProfile, opencodeProfile, opencodeZenProfile];
      return fulfill(route, { models, count: models.length });
    }

    if (path === "/api/tools/catalog") {
      return fulfill(route, {
        services: toolCatalogServices,
        tools: toolCatalogTools,
        count: toolCatalogTools.length,
      });
    }

    if (path === "/api/tools/selection/preview" && method === "POST") {
      return fulfill(route, {
        preview_id: "preview-tool-selection",
        expires_at: "2026-05-20T00:05:00Z",
        decision: {
          selected_tools: ["web_search", "github_issue_search"],
          selected_services: toolCatalogServices.slice(0, 2),
          recommendations: [
            { tool_id: "web_search", confidence: 0.8, reason: "web search requested" },
            { tool_id: "github_issue_search", confidence: 0.7, reason: "GitHub context requested" },
          ],
          permission_summary: { auto: 2, confirm: 0, block: 0 },
          metadata: {},
        },
      });
    }

    if (path === "/api/chat/conversations" && method === "GET") {
      return fulfill(route, { conversations: [{ ...conversation, messages: [] }], total: 1 });
    }

    if (path === "/api/chat/conversations" && method === "POST") {
      return fulfill(route, conversation);
    }

    if (path === "/api/chat/conversations/c-smoke/stream" && method === "POST") {
      const payload = request.postDataJSON() as Record<string, unknown>;
      options.onStreamRequest?.(payload);
      const message = {
        id: "m-assistant-streamed",
        role: "assistant",
        content: [{ type: "text", text: "Structured response accepted." }],
        raw_text: "Structured response accepted.",
        created_at: now + 1_000,
        conversation_id: "c-smoke",
        parent_id: "m-user-sent",
        children_ids: [],
        sequence_number: 4,
        finish_reason: "stop",
        usage: null,
        widget: null,
        model: "stub/default",
        metadata: {},
        events: [],
        tool_logs: [],
      };
      if (options.streamEvents) {
        return fulfillStreamEvents(route, options.streamEvents(message));
      }
      return fulfillStream(route, message);
    }

    if (path === "/api/chat/conversations/c-smoke") {
      return fulfill(route, conversation);
    }

    if ((path === "/api/conversations/c-smoke/tool-preferences" || path === "/api/chat/conversations/c-smoke/tool-preferences") && method === "PUT") {
      const payload = request.postDataJSON() as Record<string, unknown>;
      conversationToolPreferences = (payload.preferences && typeof payload.preferences === "object" && !Array.isArray(payload.preferences))
        ? payload.preferences as Record<string, unknown>
        : {};
      return fulfill(route, { conversation_id: "c-smoke", preferences: conversationToolPreferences });
    }

    if (path === "/api/conversations/c-smoke/tool-preferences" || path === "/api/chat/conversations/c-smoke/tool-preferences") {
      return fulfill(route, { conversation_id: "c-smoke", preferences: conversationToolPreferences });
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

    if (path === "/api/coding/approvals/approve" && method === "POST") {
      const payload = request.postDataJSON() as Record<string, unknown>;
      return fulfill(route, {
        request_id: payload.approval_request_id,
        approved: true,
        token: "approved-mcp-token",
      });
    }

    if (path === "/api/coding/approvals") {
      return fulfill(route, { requests: [], pending: [], count: 0 });
    }

    if (path === "/api/coding/checkpoints") {
      return fulfill(route, { checkpoints: [], workspace_id: "ws-main", workspace_root: "/repo" });
    }

    if (path === "/api/coding/rumi-log") {
      return fulfill(route, {
        rumi_dir: "/repo/.rumi",
        events_path: "/repo/.rumi/events.jsonl",
        events: [],
        summary: {
          total: 0,
          by_kind: {},
          by_status: {},
          agent_ids: [],
          commit_count: 0,
          push_count: 0,
          plan_count: 0,
          task_count: 0,
          conversation_count: 0,
          mention_count: 0,
          last_event_at: null,
          last_commit_hash: null,
        },
        workspace_id: "ws-main",
        workspace_root: "/repo",
        created: false,
      });
    }

    if (path === "/api/browser/artifacts") {
      return fulfill(route, {
        artifacts: [{ artifact_id: "browser-1", session_id: "s1", action: "browser.session", created_at: "2026-05-20T00:00:00Z", url: "https://example.com" }],
        count: 1,
      });
    }

    if (path === "/api/tools/mcp" && method === "POST") {
      const payload = request.postDataJSON() as { server?: Record<string, unknown> };
      const server = {
        server_id: String(payload.server?.server_id ?? "contract_digest"),
        name: String(payload.server?.name ?? payload.server?.server_id ?? "contract_digest"),
        transport: "stdio",
        connected: false,
        permissions: { approved: false },
        tools: [],
      };
      mcpServers.push(server);
      return fulfill(route, { server });
    }

    if (path === "/api/tools/mcp/connect" && method === "POST") {
      const payload = request.postDataJSON() as Record<string, unknown>;
      const serverId = String(payload.server_id ?? payload.server_name ?? "contract_digest");
      if (!payload.approval_token) {
        return fulfill(route, {
          approval_required: true,
          approval_request_id: "apr-mcp-contract",
          server_id: serverId,
        });
      }
      const server = mcpServers.find((item) => item.server_id === serverId);
      if (server) {
        server.connected = true;
        server.permissions = { approved: true };
        server.tools = [`mcp__${serverId}__digest`];
      }
      return fulfill(route, {
        server_id: serverId,
        server_name: serverId,
        status: "connected",
        tools: [`mcp__${serverId}__digest`],
        permission: { approved: true, source: "approval" },
      });
    }

    if (path === "/api/tools/mcp") {
      return fulfill(route, {
        servers: mcpServers,
        count: mcpServers.length,
      });
    }

    return fulfill(route, {});
  });
}

async function openDefaultspack(page: Page, path = "/chat", options: ApiMockOptions = {}) {
  await installDefaultspackApiMocks(page, options);
  await page.goto(path);
  await expect(page.getByText("Preview Calendar Chat").first()).toBeVisible();
}

async function openCodingWidget(page: Page) {
  await openDefaultspack(page, "/chat");
  await page.locator("textarea.rumi-composer-textarea").fill("/coding");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/coding(?:\?|$)/);
  const codingWidgetButton = page.getByRole("button", { name: "Coding widget" });
  await expect(codingWidgetButton).toBeVisible();
  await codingWidgetButton.click();
  await expect(page.locator(".coding-cockpit")).toBeVisible();
}

test("tool hub search suggestions close on outside click while keeping filtered actions usable", async ({ page }) => {
  await openDefaultspack(page);

  await page.locator('button[title="機能"]').click();
  const search = page.getByPlaceholder("機能を検索");
  await search.fill("web");
  await expect(page.getByTestId("tool-manager-candidates")).toBeVisible();
  await expect(page.getByTestId("tool-manager-candidates")).toContainText("Web Search");

  await page.getByRole("heading", { name: "機能" }).click();
  await expect(page.getByTestId("tool-manager-candidates")).toBeHidden();
  await expect(search).toHaveValue("web");

  await page.getByRole("button", { name: "表示中を今回使う" }).click();
  await expect(page.locator(".rumi-composer-frame")).toContainText("Web Search");
});

test("composer approval menu opens action permissions while selection modes live in settings", async ({ page }) => {
  await openDefaultspack(page);

  await page.getByRole("button", { name: "アクションの承認方法" }).click();
  const approvalMenu = page.getByRole("menu", { name: "アクションの承認方法" });
  await expect(approvalMenu).toContainText("Codex アクションの承認方法");
  await expect(approvalMenu).toContainText("承認を求める");
  await expect(approvalMenu).toContainText("代理で承認");
  await expect(approvalMenu).toContainText("フルアクセス");
  await expect(approvalMenu).toContainText("カスタム（設定）");
  await expect(approvalMenu).not.toContainText("自動で選ぶ");

  await approvalMenu.getByRole("button", { name: "詳細はこちら" }).click();
  await expect(page.getByRole("heading", { name: "機能と接続" })).toBeVisible();
  await expect(page.getByRole("button", { name: "基本", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "権限", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "接続", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "高度な設定", exact: true })).toBeVisible();
  await expect(page.getByText("既定の使い方")).toBeVisible();
  await expect(page.getByText("自動で選ぶ")).toBeVisible();

  await page.getByRole("button", { name: "権限", exact: true }).click();
  for (const label of ["読む", "検索する", "作る", "更新する", "送信する", "実行する", "コンピュータ操作", "削除・push・reset"]) {
    await expect(page.getByRole("heading", { name: label, exact: true })).toBeVisible();
  }
  await expect(page.getByText("自動で許可").first()).toBeVisible();
  await expect(page.getByText("確認する").first()).toBeVisible();
  await expect(page.getByText("使わない").first()).toBeVisible();

  await page.getByRole("button", { name: "接続", exact: true }).click();
  await expect(page.getByRole("heading", { name: "GitHub" })).toBeVisible();
  await expect(page.getByText("権限を調整").first()).toBeVisible();

  await page.getByRole("button", { name: "高度な設定", exact: true }).click();
  await expect(page.getByText("自動：ベクトルで絞って別のAIが決める")).toBeVisible();
  await expect(page.getByText("ベクトルで選ぶ", { exact: true })).toBeVisible();
  await expect(page.getByText("別のAIがすべての機能から選ぶ")).toBeVisible();
  await expect(page.getByText("すべて読み込む＋おすすめを付ける")).toBeVisible();
  await expect(page.getByText("全ツールスキーマをそのまま渡します")).toBeVisible();
  await expect(page.getByText("軽量キーワードで選ぶ")).toBeVisible();
  await expect(page.getByText("Tool補助モデル")).toBeVisible();
  await expect(page.getByText("ベクトルモデル")).toBeVisible();
  await expect(page.getByText("Text Embedding 004")).toBeVisible();
});

test("tool hub service selections can be scoped to the conversation and survive reload", async ({ page }) => {
  await openDefaultspack(page);

  await page.locator('button[title="機能"]').click();
  await page.getByRole("button", { name: "この会話" }).click();
  const githubCard = page.locator("div.rounded-md").filter({ hasText: "GitHub" }).first();
  await expect(githubCard).toBeVisible();
  await githubCard.getByTitle("サービスを使う").click();
  await expect(githubCard).toContainText("会話固定");

  await page.reload();
  await expect(page.getByText("Preview Calendar Chat").first()).toBeVisible();
  await page.locator('button[title="機能"]').click();
  await page.getByRole("button", { name: "この会話" }).click();
  const reloadedGithubCard = page.locator("div.rounded-md").filter({ hasText: "GitHub" }).first();
  await expect(reloadedGithubCard).toContainText("会話固定");
});

test("composer at mention selects tools and skills and sends mention metadata", async ({ page }) => {
  const streamRequests: Record<string, unknown>[] = [];
  await openDefaultspack(page, "/chat", {
    onStreamRequest: (payload) => streamRequests.push(payload),
  });

  const composer = page.locator("textarea.rumi-composer-textarea");
  await composer.fill("Use @web");
  const mentions = page.getByTestId("composer-at-mention-candidates");
  await expect(mentions).toBeVisible();
  await expect(mentions).toContainText("@Web Search");
  await expect(mentions).toContainText("web_search");

  await page.getByRole("option", { name: /web_search|@web search/i }).click();
  await expect(composer).toHaveValue("Use @web_search ");
  await expect(page.locator(".rumi-composer-frame")).toContainText("Web Search");

  await composer.pressSequentially("@live");
  await expect(mentions).toBeVisible();
  await expect(mentions).toContainText("@Live Review");
  await expect(mentions).toContainText("feedback/live-review");
  await page.getByRole("option", { name: /feedback\/live-review|@live review/i }).click();
  await expect(composer).toHaveValue("Use @web_search @feedback/live-review ");
  await expect(page.locator(".rumi-composer-frame")).toContainText("Live Review");

  await page.locator(".rumi-send-button").click();
  await expect.poll(() => streamRequests.length).toBe(1);

  const request = streamRequests[0];
  expect(request.tools).toEqual(["web_search"]);
  const params = request.params as Record<string, unknown>;
  const toolSelection = params.tool_selection as Record<string, unknown>;
  expect(toolSelection.mode).toBe("manual");
  expect(toolSelection.scope).toBe("turn");
  expect(toolSelection.include).toEqual([{ kind: "tool", id: "web_search" }]);

  const message = request.message as Record<string, unknown>;
  const metadata = message.metadata as Record<string, unknown>;
  expect(metadata.selected_tools).toEqual(["web_search"]);
  expect(metadata.skills).toEqual(["feedback/live-review"]);
  expect(metadata.skill_mentions).toEqual([{ id: "feedback/live-review", label: "Live Review" }]);
  expect(metadata.dropped_widgets).toEqual([
    expect.objectContaining({
      id: "web_search",
      type: "tool",
      label: "Web Search",
      widgetKind: "tool_toggle",
      sourceItemId: "web_search",
      metadata: expect.objectContaining({
        source: "composer_at_mention",
        mention: { syntax: "@web_search", tool_id: "web_search" },
        tool: expect.objectContaining({
          id: "web_search",
          label: "Web Search",
          tags: ["research"],
        }),
      }),
    }),
    expect.objectContaining({
      id: "feedback/live-review",
      type: "skill",
      label: "Live Review",
      widgetKind: "skill_prompt",
      sourceItemId: "feedback/live-review",
      metadata: expect.objectContaining({
        source: "composer_at_mention",
        mention: { syntax: "@feedback/live-review", skill_id: "feedback/live-review" },
        skill: expect.objectContaining({
          id: "feedback/live-review",
          label: "Live Review",
          aliases: ["reality", "live-review"],
        }),
      }),
    }),
  ]);
});

test("composer browser behavior covers long text popovers and mobile coding trust", async ({ page }) => {
  await openDefaultspack(page, "/chat");

  await page.getByTitle("New Chat").first().click();
  await expect(page.locator(".rumi-new-chat-stage")).toBeVisible();

  const homeComposer = page.locator("textarea.rumi-composer-textarea");
  const longPrompt = Array.from({ length: 80 }, (_, index) => `長文入力 ${index} @README.md`).join("\n");
  await homeComposer.fill(longPrompt);
  await expect(homeComposer).toHaveValue(longPrompt);
  await expect(page.locator(".rumi-composer-mention-overlay")).toHaveCount(0);
  const homeMetrics = await homeComposer.evaluate((element) => {
    const style = window.getComputedStyle(element);
    return {
      color: style.color,
      scrollHeight: element.scrollHeight,
      clientHeight: element.clientHeight,
    };
  });
  expect(homeMetrics.color).not.toBe("rgba(0, 0, 0, 0)");
  expect(homeMetrics.scrollHeight).toBeGreaterThan(homeMetrics.clientHeight);

  await homeComposer.fill("/coding");
  await expect(page.getByText("Commands")).toBeVisible();

  await openDefaultspack(page, "/coding");
  const codingComposer = page.locator("textarea.rumi-composer-textarea");
  await codingComposer.fill("@REA");
  const mentions = page.getByTestId("composer-at-mention-candidates");
  await expect(mentions).toBeVisible();
  await expect(mentions).toContainText("README.md");
  const mentionBox = await mentions.boundingBox();
  expect(mentionBox).not.toBeNull();
  expect(mentionBox!.x).toBeGreaterThanOrEqual(0);
  expect(mentionBox!.y).toBeGreaterThanOrEqual(0);
  expect(mentionBox!.x + mentionBox!.width).toBeLessThanOrEqual(page.viewportSize()!.width);

  await page.getByLabel("close mention menu").click({ position: { x: 4, y: 4 } });
  await expect(mentions).toBeHidden();

  await page.setViewportSize({ width: 390, height: 820 });
  await openDefaultspack(page, "/coding");
  const workspacePicker = page.locator(".rumi-workspace-picker");
  await expect(workspacePicker).toBeVisible();
  await expect(workspacePicker.locator("svg.text-emerald-300").first()).toBeVisible();
});

test("resizable canvas and tool widgets persist width choices", async ({ page }) => {
  await openDefaultspack(page);

  await page.getByTitle("Canvas を開く").click();
  const preview = page.getByLabel("Activity preview");
  await expect(preview).toBeVisible();
  const canvasHandle = page.getByLabel("Canvas幅を変更");
  await expect(canvasHandle).toBeVisible();
  const canvasBox = await canvasHandle.boundingBox();
  expect(canvasBox).not.toBeNull();
  await page.mouse.move(canvasBox!.x + canvasBox!.width / 2, canvasBox!.y + canvasBox!.height / 2);
  await page.mouse.down();
  await page.mouse.move(canvasBox!.x - 80, canvasBox!.y + canvasBox!.height / 2, { steps: 5 });
  await page.mouse.up();
  await expect.poll(() => page.evaluate(() => localStorage.getItem("rumi-activity-preview-width"))).not.toBeNull();
  const storedCanvasWidth = await page.evaluate(() => Number(localStorage.getItem("rumi-activity-preview-width")));
  expect(storedCanvasWidth).toBeGreaterThanOrEqual(300);

  await page.locator('button[title="機能"]').click();
  await expect(page.getByRole("heading", { name: "機能" })).toBeVisible();
  const toolHandle = page.getByLabel("機能パネル幅を変更");
  await expect(toolHandle).toBeVisible();
  const toolBox = await toolHandle.boundingBox();
  expect(toolBox).not.toBeNull();
  await page.mouse.move(toolBox!.x + toolBox!.width / 2, toolBox!.y + toolBox!.height / 2);
  await page.mouse.down();
  await page.mouse.move(toolBox!.x - 90, toolBox!.y + toolBox!.height / 2, { steps: 5 });
  await page.mouse.up();
  await expect.poll(() => page.evaluate(() => localStorage.getItem("rumi-right-sidebar-panel-width"))).not.toBeNull();
  const storedToolWidth = await page.evaluate(() => Number(localStorage.getItem("rumi-right-sidebar-panel-width")));
  expect(storedToolWidth).toBeGreaterThanOrEqual(320);
});

test("model picker search supports @provider filters", async ({ page }) => {
  await openDefaultspack(page);

  await page.getByRole("button", { name: /Stub Default/ }).click();
  const search = page.getByPlaceholder("モデルを検索... @google");
  await search.fill("@opencode");
  await expect(page.getByText("Qwen3.5 Plus via OpenCode Go")).toBeVisible();
  await expect(page.getByText("MiMo V2.5 Free via OpenCode Zen")).toBeVisible();
  await expect(page.getByText("Gemini 2.5 Flash")).toBeHidden();

  await search.fill("@opencode zen");
  await expect(page.getByText("MiMo V2.5 Free via OpenCode Zen")).toBeVisible();
  await expect(page.getByText("Qwen3.5 Plus via OpenCode Go")).toBeHidden();

  await search.fill("@google flash");
  await expect(page.getByText("Gemini 2.5 Flash")).toBeVisible();
  await expect(page.getByText("Qwen3.5 Plus via OpenCode Go")).toBeHidden();
});

test("model picker keeps unconfigured opencode zen visible for first-run setup", async ({ page }) => {
  await openDefaultspack(page);

  await page.getByRole("button", { name: /Stub Default/ }).click();
  const search = page.getByPlaceholder("モデルを検索... @google");
  await search.fill("mimo");
  await expect(page.getByText("MiMo V2.5 Free via OpenCode Zen")).toBeVisible();
});

test("preview pane opens from the chat canvas peek", async ({ page }) => {
  await openDefaultspack(page);

  await page.getByTitle("Canvas を開く").click();

  const preview = page.getByLabel("Activity preview");
  await expect(preview).toBeVisible();
  await expect(preview).toContainText("calendar-smoke.json");
});

test("calendar action renders a scheduler preview", async ({ page }) => {
  await openDefaultspack(page);

  await page.locator('button[title="機能"]').click();
  const toolManagerSearch = page.getByPlaceholder("機能を検索");
  await toolManagerSearch.fill("scheduler");
  await page.getByTestId("tool-manager-candidates").getByRole("button", { name: /Scheduler/ }).first().click();
  await expect(page.getByText("Calendar and trigger smoke surface.")).toBeVisible();
  await page.locator('button[title="Calendar"]').last().click();

  const preview = page.getByLabel("Activity preview");
  await expect(preview).toContainText("Calendar.json");
  await expect(preview).toContainText("nightly-review");
});

test("calendar mode opens quick add and renders new tasks in blue", async ({ page }) => {
  await openDefaultspack(page, "/coding");

  await page.locator('button[title="Calendar"]').first().click();
  await expect(page.getByLabel("Calendar month")).toBeVisible();

  const now = new Date();
  const dayKey = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-09`;
  const nextDayKey = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-10`;
  const nextMonth = new Date(now.getFullYear(), now.getMonth() + 1, 1);
  const nextMonthKey = `${nextMonth.getFullYear()}-${String(nextMonth.getMonth() + 1).padStart(2, "0")}-01`;
  const dayLabel = `${now.getFullYear()}年${now.getMonth() + 1}月9日`;
  const nextDayLabel = `${now.getFullYear()}年${now.getMonth() + 1}月10日`;
  await page.getByLabel("次の月").click();
  await expect(page.getByTestId(`calendar-day-${nextMonthKey}`)).toBeVisible();
  await page.getByLabel("今日").click();
  await page.getByTestId(`calendar-day-${dayKey}`).click();
  await expect(page.getByRole("dialog", { name: `${dayLabel}に追加` })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: `${dayLabel}に追加` })).toBeHidden();
  await expect(page.getByRole("dialog", { name: `${nextDayLabel}に追加` })).toBeHidden();
  await page.getByTestId(`calendar-day-${nextDayKey}`).click();
  await expect(page.getByRole("dialog", { name: `${nextDayLabel}に追加` })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByTestId(`calendar-day-${dayKey}`).click();
  await expect(page.getByRole("dialog", { name: `${dayLabel}に追加` })).toBeVisible();

  await page.getByPlaceholder("何を追加しますか？").fill("Design review");
  await page.getByRole("button", { name: "追加", exact: true }).click();

  const task = page.getByText("Design review");
  await expect(task).toBeVisible();
  await expect(task).toHaveClass(/bg-blue-500\/90/);
  await task.click();
  await expect(page.getByRole("dialog", { name: `${dayLabel}に追加` })).toContainText("項目を編集");
  await page.getByLabel("カレンダー項目の時刻").click();
  await expect(page.getByRole("listbox", { name: "カレンダー時刻候補" })).toContainText("午前12:30");
  await page.getByPlaceholder("何を追加しますか？").fill("Design review edited");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByText("Design review edited")).toBeVisible();

  const rangeStart = page.getByTestId(`${"calendar-day"}-${dayKey.replace("-09", "-12")}`);
  const rangeEnd = page.getByTestId(`${"calendar-day"}-${dayKey.replace("-09", "-14")}`);
  const startBox = await rangeStart.boundingBox();
  const endBox = await rangeEnd.boundingBox();
  expect(startBox).not.toBeNull();
  expect(endBox).not.toBeNull();
  await page.mouse.move(startBox!.x + startBox!.width / 2, startBox!.y + startBox!.height / 2);
  await page.mouse.down();
  await page.mouse.move(endBox!.x + endBox!.width / 2, endBox!.y + endBox!.height / 2, { steps: 6 });
  await page.mouse.up();
  await expect(page.getByRole("dialog", { name: `${dayLabel.replace("9日", "12日")} - ${dayLabel.replace("9日", "14日")}に追加` })).toBeVisible();
  await page.getByPlaceholder("何を追加しますか？").fill("Range task");
  await page.getByRole("button", { name: "追加", exact: true }).click();
  await expect(page.getByText("Range task")).toHaveCount(3);

  await page.getByText("Range task").first().click();
  await page.getByRole("button", { name: "削除", exact: true }).click();
  await expect(page.getByText("Range task")).toHaveCount(0);

  await page.getByTitle("Settings").last().click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
});

test("history card drag uses rumi history MIME and sends dropped_widgets metadata", async ({ page }) => {
  const streamRequests: Record<string, unknown>[] = [];
  await openDefaultspack(page, "/chat", {
    onStreamRequest: (payload) => streamRequests.push(payload),
  });

  await expect(page.getByText("Preview Calendar Chat").first()).toBeVisible();
  const composer = page.locator(".rumi-composer-frame");
  await expect(composer).toBeVisible();
  const dragEvidence = await page.evaluate((mime) => {
    const source = document.querySelector('[data-testid="history-chat-card-c-smoke"]');
    const target = document.querySelector(".rumi-composer-shell");
    if (!source || !target) throw new Error("history card or composer target not found");
    const dataTransfer = new DataTransfer();
    source.dispatchEvent(new DragEvent("dragstart", { bubbles: true, cancelable: true, dataTransfer }));
    const historyPayload = dataTransfer.getData(mime);
    target.dispatchEvent(new DragEvent("dragover", { bubbles: true, cancelable: true, dataTransfer }));
    target.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer }));
    return {
      historyPayload,
      plainText: dataTransfer.getData("text/plain"),
    };
  }, historyChatDropMime);

  expect(dragEvidence.plainText).toBe("Preview Calendar Chat");
  expect(JSON.parse(dragEvidence.historyPayload)).toMatchObject({
    conversationId: "c-smoke",
    title: "Preview Calendar Chat",
    conversationKind: "coding",
    tags: ["coding"],
  });
  await expect(composer).toContainText("Preview Calendar Chat");

  await page.locator("textarea.rumi-composer-textarea").fill("Use this dropped chat as context.");
  await page.locator(".rumi-send-button").click();
  await expect.poll(() => streamRequests.length).toBe(1);

  const request = streamRequests[0];
  const message = request.message as Record<string, unknown>;
  const metadata = message.metadata as Record<string, unknown>;
  const droppedWidgets = metadata.dropped_widgets as Array<Record<string, unknown>>;
  expect(droppedWidgets).toHaveLength(1);
  expect(droppedWidgets[0]).toMatchObject({
    id: "conversation:c-smoke",
    type: "conversation",
    widgetKind: "history_context",
    sourceItemId: "c-smoke",
    label: "Preview Calendar Chat",
  });
  expect(droppedWidgets[0].metadata).toMatchObject({
    conversation_id: "c-smoke",
    title: "Preview Calendar Chat",
  });
});

test("late stream activity after final message does not leave an empty draft pending", async ({ page }) => {
  await openDefaultspack(page, "/chat", {
    streamEvents: (message) => [
      { type: "content_delta", data: { delta: "Structured response accepted." } },
      { type: "assistant_message_completed", data: { message } },
      {
        type: "tool_call_started",
        data: {
          tool_name: "browser_use",
          tool_call_id: "call-late",
          display_text: "browser_use を使用中",
          message: "browser_use を使用中",
        },
      },
      { type: "done", data: { message } },
    ],
  });

  await page.locator("textarea.rumi-composer-textarea").fill("Use browser after final.");
  await page.locator(".rumi-send-button").click();

  await expect(page.getByText("Structured response accepted.")).toBeVisible();
  await expect(page.getByText("レスポンス本文が空でした。stream が途中で閉じたか、thinking のみで終了した可能性があります。")).toBeHidden();
  await expect(page.getByText("tool 準備中")).toBeHidden();
});

test("coding slash command toggles coding mode off again", async ({ page }) => {
  await openDefaultspack(page, "/chat");

  await page.locator("textarea.rumi-composer-textarea").fill("/coding");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/coding(?:\?|$)/);
  await expect(page.getByRole("button", { name: "Coding widget" })).toBeVisible();

  await page.locator("textarea.rumi-composer-textarea").fill("/coding");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/chat(?:\?|$)/);
  await expect(page.getByRole("button", { name: "Coding widget" })).toBeHidden();
});

test("tool timeline shows streamed activity details", async ({ page }) => {
  await openDefaultspack(page);

  await expect(page.locator(".rumi-tool-activity")).toHaveCount(1);
  const toggle = page.getByRole("button", { name: /作業状況を開く:/ });
  await expect(toggle).toBeVisible();
  await expect(toggle).toContainText("詳細");

  await toggle.click();
  const expandedToggle = page.getByRole("button", { name: /作業状況を閉じる:/ });
  await expect(expandedToggle).toBeVisible();
  await expect(expandedToggle).toContainText("閉じる");
  const timeline = page.locator(".rumi-tool-activity");
  await expect(timeline).toBeVisible();
  await expect(timeline).toContainText("ファイル");
  await expect(timeline).toContainText("src");
  await expect(timeline).toContainText("Listed 2 files");
});

test("mocked coding cockpit renders MCP server state", async ({ page }) => {
  await openCodingWidget(page);

  await expect(page.locator(".coding-cockpit")).toBeVisible();
  const mcpServers = page.getByLabel("MCP servers");
  await expect(mcpServers).toContainText("Filesystem MCP");
  await expect(mcpServers).toContainText("approved");
});

test("mocked coding cockpit registers approves and connects an MCP server", async ({ page }) => {
  await openCodingWidget(page);

  await page.getByLabel("MCP server id").fill("contract_digest");
  await page.getByLabel("MCP command").fill("python");
  await page.getByLabel("MCP args").fill("digest_server.py");
  await page.getByTitle("Connect MCP server").click();

  const mcpServers = page.getByLabel("MCP servers");
  await expect(mcpServers).toContainText("contract_digest");
  await expect(mcpServers).toContainText("approved");
  await expect(page.getByText("MCP connected: contract_digest (1 tools)")).toBeVisible();
});
