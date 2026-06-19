import test from "node:test";
import assert from "node:assert/strict";
import { ChatStreamInterruptedError, api, composerCommandResultMessage, defaultspackApiHeaders, explainDefaultspackApiError, mergeComposerCommands, normalizeChatStreamEvent, normalizeBrowserComputerApprovalAction, usesBrowserComputerApprovalEndpoint } from "./api";
import type { ComposerCommandItem } from "./api";
import { selectTemplateAiInput, selectTemplateComposerInput, selectTemplateToolPolicy, templateAiInputParamsPayload, templateComposerWidgetsForInput, templateFeatureFlagEnabled, templateToolPolicySettings } from "./templateAiInput";
import { frontendCommandArgs, keepSelectedToolsAfterSend, parseCommandBoolean, parseSlashCommandInput, resolveUltraYoloModeState, resolvedFrontendCommandArgs } from "../App";
import { shouldAutoCompactHistory } from "../App";

test("frontend command args prefer backend-coerced values", () => {
  assert.deepEqual(
    frontendCommandArgs({ enabled: "false" }, { enabled: false }),
    { enabled: false },
  );
});

test("frontend execution keeps locally parsed command args", () => {
  const command: ComposerCommandItem = {
    id: "ultra_yolo",
    name: "ultra",
    label: "Ultra Yolo",
    category: "mode",
    visibility: "default",
    risk: "medium",
    args: [{ name: "enabled", type: "boolean", required: false }],
    execution: { type: "frontend", action: "toggle_ultra_yolo" },
  };

  assert.deepEqual(
    resolvedFrontendCommandArgs(command, {}, { enabled: true }),
    {},
  );
});

test("frontend boolean command parsing handles explicit false strings", () => {
  assert.equal(parseCommandBoolean("false", true), false);
  assert.equal(parseCommandBoolean("0", true), false);
  assert.equal(parseCommandBoolean("off", true), false);
  assert.equal(parseCommandBoolean(undefined, true), true);
});

test("slash command parsing supports multi-word aliases without treating them as args", () => {
  const commands: ComposerCommandItem[] = [
    {
      id: "ultra_yolo",
      name: "ultra",
      aliases: ["ultrayolo", "ultra_yolo"],
      label: "Ultra Yolo",
      category: "mode",
      visibility: "default",
      risk: "medium",
      args: [{ name: "enabled", type: "boolean", required: false }],
      execution: { type: "frontend", action: "toggle_ultra_yolo" },
    },
  ];

  const parsed = parseSlashCommandInput("/ultra yolo", commands);
  assert.equal(parsed?.command.id, "ultra_yolo");
  assert.deepEqual(parsed?.args, {});

  const explicitOff = parseSlashCommandInput("/ultra yolo off", commands);
  assert.deepEqual(explicitOff?.args, { enabled: "off" });
});

test("slash command parsing can be disabled by template feature flags", () => {
  const commands: ComposerCommandItem[] = [
    {
      id: "context_txt",
      name: "context-txt",
      label: "Context TXT",
      category: "tools",
      visibility: "default",
      risk: "low",
      execution: { type: "pack_block", qualified_name: "defaultspack:context_txt.run" },
    },
  ];

  assert.equal(parseSlashCommandInput("/context-txt handoff", commands, { enabled: false }), null);
  assert.equal(parseSlashCommandInput("/context-txt handoff", commands)?.command.id, "context_txt");
});

test("composer command merge keeps backend command definitions authoritative", () => {
  const backendCommands: ComposerCommandItem[] = [
    {
      id: "goal",
      name: "goal",
      label: "Goal",
      category: "tools",
      visibility: "default",
      risk: "medium",
      execution: { type: "pack_block", qualified_name: "defaultspack:goal.run" },
    },
  ];
  const catalogCommands: ComposerCommandItem[] = [
    {
      id: "goal_template",
      name: "goal",
      label: "Goal Template",
      category: "tools",
      visibility: "default",
      risk: "low",
      execution: { type: "frontend", action: "template_goal_placeholder" },
    },
    {
      id: "context_txt",
      name: "context-txt",
      label: "Context TXT",
      description: "Write a context handoff file.",
      category: "tools",
      visibility: "default",
      risk: "low",
      execution: { type: "pack_block", qualified_name: "defaultspack:context_txt.run" },
    },
  ];

  const merged = mergeComposerCommands(backendCommands, catalogCommands);
  assert.deepEqual(merged.map((command) => command.id), ["goal", "context_txt"]);
  assert.deepEqual(merged[0].execution, backendCommands[0].execution);
  assert.equal(merged[0].risk, "medium");
  assert.equal(parseSlashCommandInput("/goal frontend handoff", merged)?.command.id, "goal");
  assert.equal(parseSlashCommandInput("/context-txt frontend handoff", merged)?.command.id, "context_txt");
});

test("composer command feedback surfaces pack block result messages and paths", () => {
  const command: ComposerCommandItem = {
    id: "context_txt",
    name: "context-txt",
    label: "Context TXT",
    category: "tools",
    visibility: "default",
    risk: "low",
    execution: { type: "pack_block", qualified_name: "defaultspack:context_txt.run" },
  };

  assert.equal(
    composerCommandResultMessage({
      command,
      executed: true,
      result: {
        message: "context.txt updated",
        path: "/tmp/rumi/context.txt",
      },
    }),
    "context.txt updated\n/tmp/rumi/context.txt",
  );
  assert.equal(
    composerCommandResultMessage({
      command,
      executed: true,
      result: { path: "/tmp/rumi/context.txt" },
    }),
    "Command wrote /tmp/rumi/context.txt",
  );
});

test("template ai input selects composer and tool policy metadata", () => {
  const catalog = {
    ai_inputs: [
      {
        id: "default_ai_input",
        composer_input: "default_composer",
        tool_policy: "agent_tools",
        params: { model: "template/model", max_output_tokens: 2048 },
        modes: ["agent" as const],
      },
    ],
    composer_inputs: [
      { id: "default_composer", placeholder: "Ask Rumi" },
    ],
    tool_policies: [
      {
        id: "agent_tools",
        policy: {
          default_enabled_tools: ["web_search"],
          default_disabled_tools: ["terminal"],
          allowed_tools: ["web_search", "local_file"],
          denied_tools: ["browser_computer"],
          tool_choice: "auto",
          parallel_tool_calls: true,
        },
      },
    ],
  };

  const aiInput = selectTemplateAiInput(catalog as any, "agent");
  const composerInput = selectTemplateComposerInput(catalog as any, "agent", aiInput);
  const toolPolicy = selectTemplateToolPolicy(catalog as any, "agent", aiInput);
  const settings = templateToolPolicySettings(toolPolicy);

  assert.equal(aiInput?.id, "default_ai_input");
  assert.deepEqual(templateAiInputParamsPayload(aiInput), {
    model: "template/model",
    max_output_tokens: 2048,
  });
  assert.equal(composerInput?.id, "default_composer");
  assert.equal(toolPolicy?.id, "agent_tools");
  assert.deepEqual(settings.defaultEnabledToolIds, ["web_search"]);
  assert.deepEqual(settings.defaultDisabledToolIds, ["browser_computer", "terminal"]);
  assert.deepEqual(settings.allowedToolIds, ["local_file", "web_search"]);
  assert.deepEqual(settings.deniedToolIds, ["browser_computer", "terminal"]);
  assert.equal(settings.toolChoice, "auto");
  assert.equal(settings.parallelToolCalls, true);
});

test("template ai input composes multiple active inputs and policies deterministically", () => {
  const catalog = {
    ai_inputs: [
      {
        id: "primary_ai",
        composer_input: "primary_composer",
        tool_policy: "primary_tools",
        widgets: ["web_widget"],
        modes: ["agent" as const],
      },
      {
        id: "review_ai",
        composer_input: "review_composer",
        tool_policy: "review_tools",
        widgets: ["review_widget"],
        modes: ["agent" as const],
      },
      {
        id: "coding_only_ai",
        composer_input: "coding_composer",
        modes: ["coding" as const],
      },
    ],
    composer_inputs: [
      {
        id: "primary_composer",
        placeholder: "Ask Rumi",
        accepted_modalities: ["text"],
        feature_flags: { slash_commands: false, file_attachments: true, voice_input: true },
        modes: ["agent" as const],
      },
      {
        id: "review_composer",
        help: "Review context",
        accepted_modalities: ["file", "text"],
        feature_flags: { slash_commands: true, voice_input: false },
        modes: ["agent" as const],
      },
      {
        id: "coding_composer",
        placeholder: "Coding only",
        modes: ["coding" as const],
      },
    ],
    tool_policies: [
      {
        id: "primary_tools",
        policy: {
          default_enabled_tools: ["web_search", "local_file"],
          allowed_tools: ["web_search", "local_file"],
          tool_choice: "auto",
          parallel_tool_calls: true,
        },
        modes: ["agent" as const],
      },
      {
        id: "review_tools",
        policy: {
          default_enabled_tools: ["web_search"],
          default_disabled_tools: ["terminal"],
          allowed_tools: ["web_search", "browser_computer"],
          denied_tools: ["browser_computer"],
          tool_choice: "required",
          parallel_tool_calls: false,
        },
        modes: ["agent" as const],
      },
    ],
  };

  const aiInput = selectTemplateAiInput(catalog as any, "agent");
  const composerInput = selectTemplateComposerInput(catalog as any, "agent", aiInput);
  const toolPolicy = selectTemplateToolPolicy(catalog as any, "agent", aiInput);
  const settings = templateToolPolicySettings(toolPolicy);

  assert.equal(aiInput?.id, "composed_ai_input:primary_ai+review_ai");
  assert.deepEqual(aiInput?.widgets, ["web_widget", "review_widget"]);
  assert.equal(composerInput?.id, "composed_composer_input:primary_composer+review_composer");
  assert.equal(composerInput?.placeholder, "Ask Rumi");
  assert.deepEqual(composerInput?.accepted_modalities, ["text", "file"]);
  assert.equal(templateFeatureFlagEnabled(composerInput, "slash_commands", true), false);
  assert.deepEqual(composerInput?.feature_flags, { slash_commands: false, file_attachments: true, voice_input: false });
  assert.match(toolPolicy?.id ?? "", /^composed_tool_policy:[0-9a-f]+$/);
  assert.deepEqual(settings.ids, ["primary_tools", "review_tools"]);
  assert.deepEqual(settings.allowedToolIds, ["web_search"]);
  assert.equal(settings.hasAllowedToolRestriction, true);
  assert.deepEqual(settings.deniedToolIds, ["browser_computer", "terminal"]);
  assert.deepEqual(settings.defaultEnabledToolIds, ["web_search"]);
  assert.deepEqual(settings.defaultDisabledToolIds, ["browser_computer", "terminal"]);
  assert.equal(settings.toolChoice, "auto");
  assert.deepEqual(settings.diagnostics.map((item) => item.code), ["template.tool_policy.conflicting_tool_choice"]);
  assert.equal(settings.parallelToolCalls, false);
});

test("template composer widgets become safe tool toggle widgets", () => {
  const catalog = {
    composer_widgets: [
      {
        id: "web_search_toggle",
        widget: {
          tool_id: "web_search",
          label: "Web",
          widget_kind: "tool_toggle",
        },
      },
      {
        id: "unsafe_endpoint",
        widget: {
          label: "Unsafe",
          widget_kind: "button",
          action: { type: "call_endpoint", endpoint: "/api/anything" },
        },
      },
    ],
  };

  const widgets = templateComposerWidgetsForInput(
    catalog as any,
    null,
    null,
    [{ id: "web_search", label: "Web Search", category: "tool" }],
  );

  assert.equal(widgets.length, 1);
  assert.deepEqual(widgets[0], {
    id: "web_search_toggle",
    type: "tool",
    label: "Web",
    description: undefined,
    enabled: true,
    widgetKind: "tool_toggle",
    action: { type: "toggle_tool", tool_id: "web_search" },
    sourceItemId: "web_search",
    icon: undefined,
    metadata: {
      source: "template_catalog_widget",
      template_id: null,
      piece_id: null,
      widget_id: "web_search_toggle",
      tool: {
        id: "web_search",
        label: "Web Search",
        category: "tool",
        tags: [],
      },
    },
  });
});

test("ultra yolo restore state returns to the previous yolo mode", () => {
  assert.deepEqual(
    resolveUltraYoloModeState({ yoloMode: false, ultraYoloMode: false, restoreYoloMode: false }, true),
    { yoloMode: true, ultraYoloMode: true, restoreYoloMode: false },
  );
  assert.deepEqual(
    resolveUltraYoloModeState({ yoloMode: true, ultraYoloMode: true, restoreYoloMode: false }, false),
    { yoloMode: false, ultraYoloMode: false, restoreYoloMode: false },
  );
  assert.deepEqual(
    resolveUltraYoloModeState({ yoloMode: true, ultraYoloMode: true, restoreYoloMode: true }, false),
    { yoloMode: true, ultraYoloMode: false, restoreYoloMode: false },
  );
});

test("history sidebar auto-compacts on narrow screens", () => {
  assert.equal(shouldAutoCompactHistory(390), true);
  assert.equal(shouldAutoCompactHistory(759), true);
  assert.equal(shouldAutoCompactHistory(760), false);
});

test("executeUiCommand preserves model candidate results", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => new Response(JSON.stringify({
    status: "ok",
    data: {
      command: {
        id: "model",
        name: "model",
        label: "Model",
        category: "model",
        visibility: "default",
        risk: "low",
        execution: { type: "model_command", action: "select_or_suggest_model" },
      },
      action: "show_model_candidates",
      message: "Choose a model",
      candidates: [
        {
          profile_id: "openai/gpt-5.1",
          display_name: "GPT-5.1",
          subtitle: "OpenAI / gpt-5.1",
          requires_api_key: true,
        },
      ],
      selected_model: {
        profile_id: "google/gemini-2.5-flash",
        display_name: "Gemini 2.5 Flash",
        provider_id: "google",
        model_id: "gemini-2.5-flash",
        api_key_configured: true,
      },
    },
  }), { status: 200, headers: { "Content-Type": "application/json" } })) as typeof fetch;

  try {
    const result = await api.executeUiCommand({ command: "model", args: { query: "gpt" } });
    assert.equal(result.action, "show_model_candidates");
    assert.equal(result.message, "Choose a model");
    assert.equal(result.candidates?.[0]?.profile_id, "openai/gpt-5.1");
    assert.equal(result.candidates?.[0]?.requires_api_key, true);
    const selectedModel = result.selected_model as { profile_id?: string; api_key_configured?: boolean } | null | undefined;
    if (!selectedModel) {
      assert.fail("expected selected_model to be a model candidate object");
    }
    assert.equal(selectedModel.profile_id, "google/gemini-2.5-flash");
    assert.equal(selectedModel.api_key_configured, true);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("listModelProfiles bypasses browser cache", async () => {
  let requestUrl = "";
  let requestCache: RequestCache | undefined;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    requestUrl = String(input);
    requestCache = init?.cache;
    return new Response(JSON.stringify({
      status: "ok",
      data: {
        profiles: [],
        count: 0,
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    const result = await api.listModelProfiles();
    assert.equal(result.count, 0);
    assert.deepEqual(result.profiles, []);
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(requestUrl, "/api/ai/profiles");
  assert.equal(requestCache, "no-store");
});

test("kanban API methods use first-class board and card routes", async () => {
  const requests: Array<{ input: string; init?: RequestInit }> = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    requests.push({ input: String(input), init });
    if (String(input).startsWith("/api/kanban/boards?")) {
      return new Response(JSON.stringify({
        status: "ok",
        data: {
          board: {
            board_id: "board-1",
            scope_type: "conversation",
            scope_id: "conv 1",
            title: "Chat board",
          },
          columns: [],
          cards: [],
        },
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (String(input).endsWith("/import-conversation")) {
      return new Response(JSON.stringify({
        status: "ok",
        data: {
          board: {
            board_id: "board-1",
            scope_type: "conversation",
            scope_id: "conv 1",
            title: "Chat board",
          },
          columns: [],
          cards: [{ card_id: "card-imported", board_id: "board-1", column_id: "col-1", position: 1000, title: "Imported" }],
        },
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    return new Response(JSON.stringify({
      status: "ok",
      data: {
        card_id: "card-1",
        board_id: "board-1",
        column_id: "col-1",
        position: 1000,
        title: "Fix UI",
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    const board = await api.kanbanGetOrCreateBoard({ type: "conversation", id: "conv 1" });
    const card = await api.kanbanCreateCard("board-1", { title: "Fix UI", column_id: "col-1" });
    const imported = await api.kanbanImportConversation("board-1", { conversation_id: "conv 1", column_id: "col-1" });

    assert.equal(board.board.board_id, "board-1");
    assert.equal(card.card_id, "card-1");
    assert.equal(imported.cards[0]?.card_id, "card-imported");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(requests[0]?.input, "/api/kanban/boards?scope_type=conversation&scope_id=conv+1&bootstrap=true");
  assert.equal(requests[0]?.init?.cache, "no-store");
  assert.equal(requests[1]?.input, "/api/kanban/boards/board-1/cards");
  assert.equal(requests[1]?.init?.method, "POST");
  assert.deepEqual(JSON.parse(String(requests[1]?.init?.body ?? "{}")), { title: "Fix UI", column_id: "col-1" });
  assert.equal(requests[2]?.input, "/api/kanban/boards/board-1/import-conversation");
  assert.equal(requests[2]?.init?.method, "POST");
  assert.deepEqual(JSON.parse(String(requests[2]?.init?.body ?? "{}")), { conversation_id: "conv 1", column_id: "col-1" });
});

test("defaultspack API errors include status and recovery context", () => {
  const message = explainDefaultspackApiError(403, {
    code: "FORBIDDEN",
    message: "tool approval denied",
  }, "Forbidden");

  assert.match(message, /HTTP 403 Forbidden/);
  assert.match(message, /FORBIDDEN/);
  assert.match(message, /tool approval denied/);
  assert.match(message, /権限|承認/);
});

test("selected tools are cleared after send unless settings opt in", () => {
  assert.equal(keepSelectedToolsAfterSend({}), false);
  assert.equal(keepSelectedToolsAfterSend({ tools: { keep_selected_tools_after_send: "false" } }), false);
  assert.equal(keepSelectedToolsAfterSend({ tools: { keep_selected_tools_after_send: true } }), true);
});

test("sendMessage serializes attachments and selected tools", async () => {
  let requestBody: any = null;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    requestBody = JSON.parse(String(init?.body ?? "{}"));
    return new Response(JSON.stringify({
      status: "ok",
      data: {
        id: "m1",
        role: "assistant",
        content: "ok",
        created_at: 1,
        conversation_id: "c1",
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.sendMessage("c1", "hello", {
      thinking_level: "medium",
      attachments: [
        { name: "notes.txt", content: "body", size: 4, type: "text/plain" },
        { name: "photo.png", size: 1024, type: "image/png", truncated: false },
      ],
      tools: ["local_file"],
      tool_selection: { mode: "manual", include: ["local_file"], scope: "turn", must_use: false },
      tool_policy: { selected_tools: ["local_file"] },
      metadata: { selected_tools: ["local_file"] },
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(requestBody?.message, {
    role: "user",
    content: "hello",
    attachments: [
      { name: "notes.txt", content: "body", size: 4, type: "text/plain" },
      { name: "photo.png", size: 1024, type: "image/png", truncated: false },
    ],
    metadata: { selected_tools: ["local_file"] },
  });
  assert.deepEqual(requestBody?.tools, ["local_file"]);
  assert.deepEqual(requestBody?.params, {
    thinking_level: "medium",
    tool_policy: { selected_tools: ["local_file"] },
    tool_selection: { mode: "manual", include: ["local_file"], scope: "turn", must_use: false },
  });
});

test("sendMessage preserves an empty selected tools filter", async () => {
  let requestBody: any = null;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    requestBody = JSON.parse(String(init?.body ?? "{}"));
    return new Response(JSON.stringify({
      status: "ok",
      data: {
        id: "m-empty-tools",
        role: "assistant",
        content: "ok",
        created_at: 1,
        conversation_id: "c1",
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.sendMessage("c1", "hello", {
      tools: [],
      tool_policy: { selected_tools: [] },
      metadata: { selected_tools: [] },
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(requestBody?.tools, []);
  assert.deepEqual(requestBody?.params?.tool_policy, { selected_tools: [] });
  assert.deepEqual(requestBody?.message?.metadata, { selected_tools: [] });
});

test("sendMessage preserves authority followup display metadata", async () => {
  let requestBody: any = null;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    requestBody = JSON.parse(String(init?.body ?? "{}"));
    return new Response(JSON.stringify({
      status: "ok",
      data: {
        id: "m-authority-followup",
        role: "assistant",
        content: "ok",
        created_at: 1,
        conversation_id: "c1",
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.sendMessage("c1", "ユーザーがモデル/API の使用を許可しました。承認済みのリクエストとして続行してください。", {
      metadata: {
        authority_followup: {
          request_id: "approval-1",
          permission_id: "model.invoke",
          approval_token: "token-1",
          hidden: true,
        },
        chat_display: {
          hidden: true,
          reason: "authority_followup",
        },
        runtime_content: "continue with approved authority",
      },
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(requestBody?.message?.metadata?.authority_followup, {
    request_id: "approval-1",
    permission_id: "model.invoke",
    approval_token: "token-1",
    hidden: true,
  });
  assert.deepEqual(requestBody?.message?.metadata?.chat_display, {
    hidden: true,
    reason: "authority_followup",
  });
  assert.equal(requestBody?.message?.metadata?.runtime_content, "continue with approved authority");
});

test("approveAuthorityApproval serializes bundled related permissions", async () => {
  let requestBody: any = null;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    requestBody = JSON.parse(String(init?.body ?? "{}"));
    return new Response(JSON.stringify({
      status: "ok",
      data: {
        request_id: "approval-1",
        approved: true,
        scope: "once",
        token: "token-1",
        permission_id: "model.invoke",
        related_approvals: [],
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.approveAuthorityApproval("approval-1", {
      scope: "once",
      related_permissions: ["api_key.use"],
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(requestBody?.related_permissions, ["api_key.use"]);
});

test("testPromptStudio posts draft input and selected tools", async () => {
  let requestUrl = "";
  let requestBody: any = null;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    requestUrl = String(input);
    requestBody = JSON.parse(String(init?.body ?? "{}"));
    return new Response(JSON.stringify({
      status: "ok",
      data: {
        profile_id: "prompt-profile",
        prompt_id: "default_chat",
        segments: [],
        matched_skills: [],
        verdicts: [],
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.testPromptStudio({
      profile_id: "prompt-profile",
      prompt_id: "default_chat",
      draft: "Use the calculator when arithmetic is requested.",
      user_text: "計算して",
      selected_tools: ["calculator"],
      model_profile_id: "openai/gpt-5.1",
      model: "openai/gpt-5.1",
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(requestUrl, "/api/prompts/test");
  assert.deepEqual(requestBody, {
    profile_id: "prompt-profile",
    prompt_id: "default_chat",
    draft: "Use the calculator when arithmetic is requested.",
    user_text: "計算して",
    selected_tools: ["calculator"],
    model_profile_id: "openai/gpt-5.1",
    model: "openai/gpt-5.1",
  });
});

test("searchConversations serializes spotlight search filters", async () => {
  let requestUrl = "";
  let requestBody: any = null;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    requestUrl = String(input);
    requestBody = JSON.parse(String(init?.body ?? "{}"));
    return new Response(JSON.stringify({
      status: "ok",
      data: { results: [], total: 0, query: "weather" },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.searchConversations("weather", {
      date_filter: "7d",
      is_starred: true,
      role: "user",
      limit: 9,
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(requestUrl, "/api/chat/search");
  assert.deepEqual(requestBody, {
    query: "weather",
    mode: "conversations",
    date_filter: "7d",
    is_starred: true,
    role: "user",
    limit: 9,
    offset: 0,
  });
});

test("saveProviderApiKey serializes named API metadata", async () => {
  let requestBody: any = null;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    requestBody = JSON.parse(String(init?.body ?? "{}"));
    return new Response(JSON.stringify({
      status: "ok",
      data: { provider_id: "google", configured: true },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.saveProviderApiKey("google", "secret", {
      apiId: "main",
      name: "Main",
      baseUrl: "https://example.test/v1",
      allowedModels: ["gemini-test"],
      defaultModel: "gemini-test",
      quotaLabel: "paid",
      notes: "fast route",
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(requestBody, {
    provider_id: "google",
    value: "secret",
    api_id: "main",
    name: "Main",
    base_url: "https://example.test/v1",
    allowed_models: ["gemini-test"],
    default_model: "gemini-test",
    quota_label: "paid",
    notes: "fast route",
  });
});

test("renameProviderApiKey serializes rename action", async () => {
  let requestBody: any = null;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    requestBody = JSON.parse(String(init?.body ?? "{}"));
    return new Response(JSON.stringify({
      status: "ok",
      data: { provider_id: "google", api_id: "main", configured: true },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.renameProviderApiKey("google", "main", "work");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(requestBody, {
    action: "rename",
    provider_id: "google",
    api_id: "main",
    name: "work",
    new_api_id: "work",
  });
});

test("deleteProviderApiKey serializes delete action", async () => {
  let requestBody: any = null;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    requestBody = JSON.parse(String(init?.body ?? "{}"));
    return new Response(JSON.stringify({
      status: "ok",
      data: { provider_id: "google", api_id: "main", configured: false },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.deleteProviderApiKey("google", "main");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(requestBody, {
    action: "delete",
    provider_id: "google",
    api_id: "main",
  });
});

test("saveExternalToken serializes named token metadata", async () => {
  let requestBody: any = null;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    requestBody = JSON.parse(String(init?.body ?? "{}"));
    return new Response(JSON.stringify({
      status: "ok",
      data: { provider_id: "line", token_id: "main", configured: true },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.saveExternalToken("line", "secret", { tokenId: "main", name: "Main", kind: "channel_access_token" });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(requestBody, {
    provider_id: "line",
    token_id: "main",
    name: "Main",
    kind: "channel_access_token",
    value: "secret",
  });
});

test("streamMessage serializes auto tool selection without tools", async () => {
  let requestBody: any = null;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    requestBody = JSON.parse(String(init?.body ?? "{}"));
    const body = [
      'data: {"type":"message","message":{"id":"m2","role":"assistant","content":[{"type":"text","text":"ok"}],"created_at":1,"conversation_id":"c1"}}\n\n',
    ].join("");
    return new Response(body, {
      status: 200,
      headers: { "Content-Type": "text/event-stream; charset=utf-8" },
    });
  }) as typeof fetch;

  try {
    await api.streamMessage("c1", "hello", {
      params: { model: "template/model", max_output_tokens: 2048 },
      thinking_level: "medium",
      tool_selection: { mode: "auto", include: [], exclude: [], scope: "turn", must_use: false },
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(requestBody?.tools, undefined);
  assert.equal(requestBody?.params?.model, "template/model");
  assert.equal(requestBody?.params?.max_output_tokens, 2048);
  assert.equal(requestBody?.params?.thinking_level, "medium");
  assert.deepEqual(requestBody?.params?.tool_selection, {
    mode: "auto",
    include: [],
    exclude: [],
    scope: "turn",
    must_use: false,
  });
  assert.equal(requestBody?.params?.tool_choice, undefined);
});

test("deleteExternalToken serializes delete action", async () => {
  let requestBody: any = null;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    requestBody = JSON.parse(String(init?.body ?? "{}"));
    return new Response(JSON.stringify({
      status: "ok",
      data: { provider_id: "line", token_id: "main", configured: false },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.deleteExternalToken("line", "main");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(requestBody, {
    action: "delete",
    provider_id: "line",
    token_id: "main",
  });
});

test("streamMessage parses SSE deltas and final message", async () => {
  const originalFetch = globalThis.fetch;
  const events: string[] = [];
  let finalId = "";
  globalThis.fetch = (async () => {
    const body = [
      'data: {"type":"delta","delta":"he"}\n\n',
      'data: {"type":"delta","delta":"llo"}\n\n',
      'data: {"type":"message","message":{"id":"m2","role":"assistant","content":[{"type":"text","text":"hello"}],"created_at":1,"conversation_id":"c1"}}\n\n',
      'data: {"type":"done","message":{"id":"m2","role":"assistant","content":[{"type":"text","text":"hello"}],"created_at":1,"conversation_id":"c1"}}\n\n',
    ].join("");
    return new Response(body, {
      status: 200,
      headers: { "Content-Type": "text/event-stream; charset=utf-8" },
    });
  }) as typeof fetch;

  try {
    const final = await api.streamMessage("c1", "hello", undefined, {
      onDelta(delta) {
        events.push(delta);
      },
      onMessage(message) {
        finalId = message.id;
      },
    });
    assert.equal(final?.id, "m2");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(events, ["he", "llo"]);
  assert.equal(finalId, "m2");
});

test("streamMessage accepts canonical defaultspack stream events", async () => {
  const originalFetch = globalThis.fetch;
  const events: string[] = [];
  let finalId = "";
  globalThis.fetch = (async () => {
    const finalMessage = {
      id: "m2",
      role: "assistant",
      content: [{ type: "text", text: "hello" }],
      raw_text: "hello",
      created_at: 1,
      conversation_id: "c1",
    };
    const body = [
      `data: ${JSON.stringify({ type: "content_delta", data: { delta: "he" } })}\n\n`,
      `data: ${JSON.stringify({ type: "content_delta", data: { delta: "llo" } })}\n\n`,
      `data: ${JSON.stringify({ type: "assistant_message_completed", data: { message: finalMessage } })}\n\n`,
      `data: ${JSON.stringify({ type: "done", data: { message: finalMessage } })}\n\n`,
    ].join("");
    return new Response(body, {
      status: 200,
      headers: { "Content-Type": "text/event-stream; charset=utf-8" },
    });
  }) as typeof fetch;

  try {
    const final = await api.streamMessage("c1", "hello", undefined, {
      onDelta(delta) {
        events.push(delta);
      },
      onMessage(message) {
        finalId = message.id;
      },
    });
    assert.equal(final?.id, "m2");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(events, ["he", "llo"]);
  assert.equal(finalId, "m2");
});

test("normalizeChatStreamEvent lifts canonical activity data", () => {
  assert.deepEqual(normalizeChatStreamEvent({
    type: "tool_call_started",
    data: {
      tool_name: "browser_use",
      tool_call_id: "call-1",
      message: "browser_use を使用中",
    },
    message: "tool started",
  }), {
    type: "tool_call_started",
    tool_name: "browser_use",
    tool_call_id: "call-1",
    message: "browser_use を使用中",
  });
});

test("streamMessage forwards thinking deltas", async () => {
  const originalFetch = globalThis.fetch;
  const thinkingEvents: string[] = [];
  globalThis.fetch = (async () => {
    const body = [
      'data: {"type":"thinking_delta","delta":"private "}\n\n',
      'data: {"type":"thinking_delta","delta":"plan"}\n\n',
      'data: {"type":"delta","delta":"done"}\n\n',
      'data: {"type":"message","message":{"id":"m2","role":"assistant","content":[{"type":"text","text":"done"}],"created_at":1,"conversation_id":"c1"}}\n\n',
    ].join("");
    return new Response(body, {
      status: 200,
      headers: { "Content-Type": "text/event-stream; charset=utf-8" },
    });
  }) as typeof fetch;

  try {
    await api.streamMessage("c1", "hello", undefined, {
      onThinkingDelta(delta) {
        thinkingEvents.push(delta);
      },
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(thinkingEvents, ["private ", "plan"]);
});

test("streamMessage forwards realtime tool activity events", async () => {
  const originalFetch = globalThis.fetch;
  const activityEvents: string[] = [];
  globalThis.fetch = (async () => {
    const body = [
      'data: {"type":"status","message":"toolを接続しました","phase":"tools_attached"}\n\n',
      'data: {"type":"tool_call_started","tool_name":"browser_computer","tool_call_id":"call_1","arguments":{"action":"computer.screenshot"},"message":"browser_computer を使用中"}\n\n',
      'data: {"type":"message","message":{"id":"m2","role":"assistant","content":[{"type":"text","text":"done"}],"created_at":1,"conversation_id":"c1"}}\n\n',
    ].join("");
    return new Response(body, {
      status: 200,
      headers: { "Content-Type": "text/event-stream; charset=utf-8" },
    });
  }) as typeof fetch;

  try {
    await api.streamMessage("c1", "hello", undefined, {
      onEvent(event) {
        activityEvents.push(event.type);
      },
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(activityEvents, ["status", "tool_call_started", "message"]);
});

test("streamMessage forwards explicit browser screenshot events", async () => {
  const originalFetch = globalThis.fetch;
  const activityEvents: string[] = [];
  globalThis.fetch = (async () => {
    const body = [
      'data: {"type":"browser_screenshot","tool_name":"browser_computer","tool_call_id":"call_1","data_url":"data:image/png;base64,abc"}\n\n',
      'data: {"type":"message","message":{"id":"m2","role":"assistant","content":[{"type":"text","text":"done"}],"created_at":1,"conversation_id":"c1"}}\n\n',
    ].join("");
    return new Response(body, {
      status: 200,
      headers: { "Content-Type": "text/event-stream; charset=utf-8" },
    });
  }) as typeof fetch;

  try {
    await api.streamMessage("c1", "hello", undefined, {
      onEvent(event) {
        activityEvents.push(event.type);
      },
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(activityEvents, ["browser_screenshot", "message"]);
});

test("streamMessage forwards browser state snapshot events", async () => {
  const originalFetch = globalThis.fetch;
  const activityEvents: string[] = [];
  globalThis.fetch = (async () => {
    const body = [
      'data: {"type":"browser_state_snapshot","tool_name":"browser_computer","tool_call_id":"call_1","state_revision":7,"snapshot":{"active_window":{"title":"Example"}}}\n\n',
      'data: {"type":"message","message":{"id":"m2","role":"assistant","content":[{"type":"text","text":"done"}],"created_at":1,"conversation_id":"c1"}}\n\n',
    ].join("");
    return new Response(body, {
      status: 200,
      headers: { "Content-Type": "text/event-stream; charset=utf-8" },
    });
  }) as typeof fetch;

  try {
    await api.streamMessage("c1", "hello", undefined, {
      onEvent(event) {
        activityEvents.push(event.type);
      },
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(activityEvents, ["browser_state_snapshot", "message"]);
});

test("streamMessage surfaces structured stream errors", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => {
    return new Response('data: {"type":"error","error":{"code":"STREAM_FAILED","message":"thinking-only stream"}}\n\n', {
      status: 200,
      headers: { "Content-Type": "text/event-stream; charset=utf-8" },
    });
  }) as typeof fetch;

  try {
    await assert.rejects(
      api.streamMessage("c1", "hello"),
      /thinking-only stream/,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("streamMessage rejects streams without a final message", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => {
    return new Response('data: {"type":"delta","delta":"partial"}\n\n', {
      status: 200,
      headers: { "Content-Type": "text/event-stream; charset=utf-8" },
    });
  }) as typeof fetch;

  try {
    await assert.rejects(
      api.streamMessage("c1", "hello"),
      (error) => error instanceof ChatStreamInterruptedError && error.partialText === "partial",
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("reportClientEvent posts diagnostics to the UI contract endpoint", async () => {
  const originalFetch = globalThis.fetch;
  let requestUrl = "";
  let requestBody = "";
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    requestUrl = String(input);
    requestBody = String(init?.body ?? "");
    return new Response(JSON.stringify({
      status: "ok",
      data: { recorded: true, diagnostic_id: "diag-1" },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    const result = await api.reportClientEvent({
      category: "window_error",
      message: "Renderer crashed",
    });
    assert.equal(requestUrl, "/api/ui/client-events");
    assert.match(requestBody, /Renderer crashed/);
    assert.equal(result.recorded, true);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("streamMessage forwards abort signal to fetch", async () => {
  const originalFetch = globalThis.fetch;
  const controller = new AbortController();
  let seenSignal: AbortSignal | undefined;
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    seenSignal = init?.signal ?? undefined;
    return new Response(JSON.stringify({
      status: "ok",
      data: {
        id: "m3",
        role: "assistant",
        content: "ok",
        created_at: 1,
        conversation_id: "c1",
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.streamMessage("c1", "hello", undefined, { signal: controller.signal });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(seenSignal, controller.signal);
});

test("stopMessage calls backend stop endpoint", async () => {
  const originalFetch = globalThis.fetch;
  let requestUrl = "";
  let requestMethod = "";
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    requestUrl = String(input);
    requestMethod = String(init?.method ?? "");
    return new Response(JSON.stringify({
      status: "ok",
      data: { success: true, conversation_id: "c1", cancelled: true },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    const result = await api.stopMessage("c1");
    assert.equal(requestUrl, "/api/chat/conversations/c1/stop");
    assert.equal(requestMethod, "POST");
    assert.equal(result.cancelled, true);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("unsafe API requests include a local CSRF header", async () => {
  const originalFetch = globalThis.fetch;
  let requestHeaders: Headers | null = null;
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    requestHeaders = new Headers(init?.headers);
    return new Response(JSON.stringify({
      status: "ok",
      data: { cancelled: true },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.stopMessage("c1");
  } finally {
    globalThis.fetch = originalFetch;
  }

  const headers = requestHeaders as Headers | null;
  assert.ok(headers);
  assert.ok(headers.get("X-Rumi-CSRF"));
});

test("safe API requests do not include a local CSRF header", async () => {
  const originalFetch = globalThis.fetch;
  let requestHeaders: Headers | null = null;
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    requestHeaders = new Headers(init?.headers);
    return new Response(JSON.stringify({
      status: "ok",
      data: { conversations: [], total: 0 },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.listConversations();
  } finally {
    globalThis.fetch = originalFetch;
  }

  const headers = requestHeaders as Headers | null;
  assert.ok(headers);
  assert.equal(headers.get("X-Rumi-CSRF"), null);
});

test("streamMessage includes a local CSRF header", async () => {
  const originalFetch = globalThis.fetch;
  let requestHeaders: Headers | null = null;
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    requestHeaders = new Headers(init?.headers);
    return new Response(JSON.stringify({
      status: "ok",
      data: {
        id: "m1",
        role: "assistant",
        content: "ok",
        created_at: 1,
        conversation_id: "c1",
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.streamMessage("c1", "hello");
  } finally {
    globalThis.fetch = originalFetch;
  }

  const headers = requestHeaders as Headers | null;
  assert.ok(headers);
  assert.ok(headers.get("X-Rumi-CSRF"));
});

test("unsafe API headers replace blank CSRF values", () => {
  const headers = defaultspackApiHeaders("POST", { "X-Rumi-CSRF": " " });

  assert.ok(headers.get("X-Rumi-CSRF")?.trim());
});

test("unsafe API headers prefer panel session CSRF when present", () => {
  const previousDescriptor = Object.getOwnPropertyDescriptor(globalThis, "sessionStorage");
  const values = new Map<string, string>([
    ["rumi-panel-csrf", "panel-csrf-from-bootstrap"],
    ["rumi-defaultspack-csrf", "local-defaultspack-csrf"],
  ]);
  Object.defineProperty(globalThis, "sessionStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => {
        values.set(key, value);
      },
      removeItem: (key: string) => {
        values.delete(key);
      },
    },
  });

  try {
    const headers = defaultspackApiHeaders("PUT");
    assert.equal(headers.get("X-Rumi-CSRF"), "panel-csrf-from-bootstrap");
  } finally {
    if (previousDescriptor) {
      Object.defineProperty(globalThis, "sessionStorage", previousDescriptor);
    } else {
      Reflect.deleteProperty(globalThis, "sessionStorage");
    }
  }
});

test("browserComputer calls dedicated browser-computer endpoint", async () => {
  const originalFetch = globalThis.fetch;
  let requestUrl = "";
  let requestBody: any = null;
  let requestHeaders: Headers | null = null;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    requestUrl = String(input);
    requestBody = JSON.parse(String(init?.body ?? "{}"));
    requestHeaders = new Headers(init?.headers);
    return new Response(JSON.stringify({
      status: "ok",
      data: { handled: true },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    const result = await api.browserComputer("computer.screenshot", { reason: "test" });
    assert.equal(requestUrl, "/api/tools/browser-computer");
    assert.deepEqual(requestBody, {
      action: "computer.screenshot",
      payload: { reason: "test" },
    });
    const headers = requestHeaders as Headers | null;
    assert.ok(headers?.get("X-Rumi-CSRF"));
    assert.deepEqual(result, { handled: true });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("invokeTool calls generic tool endpoint with tool name and arguments", async () => {
  const originalFetch = globalThis.fetch;
  let requestUrl = "";
  let requestBody: any = null;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    requestUrl = String(input);
    requestBody = JSON.parse(String(init?.body ?? "{}"));
    return new Response(JSON.stringify({
      status: "ok",
      data: { handled: true },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    const result = await api.invokeTool("computer_use", { action: "computer.click", approval_token: "tok" });
    assert.equal(requestUrl, "/api/tools/invoke");
    assert.deepEqual(requestBody, {
      tool_name: "computer_use",
      arguments: { action: "computer.click", approval_token: "tok" },
    });
    assert.deepEqual(result, { handled: true });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("browser computer approvals use the browser-computer endpoint for computer_use", async () => {
  const originalFetch = globalThis.fetch;
  let requestUrl = "";
  let requestBody: any = null;
  let requestHeaders: Headers | null = null;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    requestUrl = String(input);
    requestBody = JSON.parse(String(init?.body ?? "{}"));
    requestHeaders = new Headers(init?.headers);
    return new Response(JSON.stringify({
      status: "ok",
      data: { approved: true },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    const result = await api.approveBrowserComputerAction("computer_use", "screenshot", {
      app: "Google Chrome",
      approval_token: "tok",
    });
    assert.equal(requestUrl, "/api/tools/browser-computer");
    assert.deepEqual(requestBody, {
      action: "computer.screenshot",
      payload: { app: "Google Chrome", approval_token: "tok" },
    });
    const headers = requestHeaders as Headers | null;
    assert.ok(headers?.get("X-Rumi-CSRF"));
    assert.deepEqual(result, { approved: true });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("browser approval helpers identify visible computer tools", () => {
  assert.equal(usesBrowserComputerApprovalEndpoint("computer_use"), true);
  assert.equal(usesBrowserComputerApprovalEndpoint("browser_use"), true);
  assert.equal(usesBrowserComputerApprovalEndpoint("browser_open_url"), true);
  assert.equal(usesBrowserComputerApprovalEndpoint("open_browser"), true);
  assert.equal(usesBrowserComputerApprovalEndpoint("other_tool"), false);
  assert.equal(normalizeBrowserComputerApprovalAction("computer_use", "context"), "computer.context");
  assert.equal(normalizeBrowserComputerApprovalAction("computer_use", "computer.screenshot"), "computer.screenshot");
  assert.equal(normalizeBrowserComputerApprovalAction("browser_open_url", "open_url"), "browser.open_url");
  assert.equal(normalizeBrowserComputerApprovalAction("open_browser", "open_browser"), "browser.open_url");
});

test("browser open aliases use the browser-computer approval endpoint", async () => {
  const originalFetch = globalThis.fetch;
  let requestUrl = "";
  let requestBody: any = null;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    requestUrl = String(input);
    requestBody = JSON.parse(String(init?.body ?? "{}"));
    return new Response(JSON.stringify({
      status: "ok",
      data: { approved: true },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    const result = await api.approveBrowserComputerAction("browser_open_url", "open_url", {
      url: "https://gemini.google.com",
      approval_token: "tok",
    });
    assert.equal(requestUrl, "/api/tools/browser-computer");
    assert.deepEqual(requestBody, {
      action: "browser.open_url",
      payload: { url: "https://gemini.google.com", approval_token: "tok" },
    });
    assert.deepEqual(result, { approved: true });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("authority request helpers use pending list and single request routes", async () => {
  const originalFetch = globalThis.fetch;
  const seen: string[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    seen.push(String(input));
    return new Response(JSON.stringify({
      status: "ok",
      data: String(input).includes("/auth_1")
        ? {
          request_id: "auth_1",
          status: "pending",
          principal_id: "profile:work",
          permission_id: "model.invoke",
          resource: { provider_id: "openai" },
          reason: "model access",
          risk_level: "medium",
          created_at: "2026-01-01T00:00:00Z",
          allowed_scopes: ["once", "profile"],
        }
        : { requests: [], pending: [], count: 0 },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.listAuthorityRequests({ status: "pending" });
    const request = await api.getAuthorityRequest("auth_1");
    assert.equal(request.request_id, "auth_1");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(seen, [
    "/api/authority/requests?status=pending",
    "/api/authority/requests/auth_1",
  ]);
});

test("authority approval helpers send signed ui operator provenance", async () => {
  const originalFetch = globalThis.fetch;
  const seen: Array<{ input: string; body: any; csrf: string | null }> = [];
  const uiOperator = {
    version: 1,
    kind: "ui_operator" as const,
    origin: "tauri_webview_window",
    window_label: "authority-approval",
    request_id: "auth_1",
    issued_at: 1700000000,
    expires_at: 1700000180,
    nonce: "nonce",
    signature: "sig",
  };
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const headers = new Headers(init?.headers);
    seen.push({
      input: String(input),
      body: JSON.parse(String(init?.body ?? "{}")),
      csrf: headers.get("X-Rumi-CSRF"),
    });
    return new Response(JSON.stringify({
      status: "ok",
      data: String(input).endsWith("/deny")
        ? { request_id: "auth_1", denied: true }
        : { request_id: "auth_1", approved: true, scope: "conversation" },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.approveAuthorityApproval("auth_1", {
      scope: "conversation",
      config: { provider_ids: ["openai"] },
      ui_operator: uiOperator,
    });
    await api.denyAuthorityApproval("auth_1", {
      reason: "no",
      persist: true,
      ui_operator: uiOperator,
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(seen[0].body, {
    scope: "conversation",
    config: { provider_ids: ["openai"] },
    ui_operator: uiOperator,
  });
  assert.ok(seen[0].csrf);
  assert.deepEqual(seen[1].body, {
    reason: "no",
    persist: true,
    ui_operator: uiOperator,
  });
  assert.ok(seen[1].csrf);
});

test("coding context, branch, and workspace read helpers use existing API routes", async () => {
  const seen: Array<{ input: string; body?: unknown }> = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    seen.push({ input: String(input), body: init?.body ? JSON.parse(String(init.body)) : undefined });
    return new Response(JSON.stringify({
      status: "ok",
      data: String(input).includes("/api/coding/context")
        ? { branch: "main", root_folder: "/repo", directory: "src", files: [], entries: [], git: null }
        : String(input).includes("/api/coding/files/read")
          ? { path: "README.md", content: "hello", size: 5, encoding: "utf-8" }
          : { branch: "feature", branches: ["main", "feature"], switched: true, created: true },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.getCodingContext({ directory: "src" });
    await api.switchGitBranch("feature", true);
    await api.readWorkspaceFile("README.md");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(seen[0].input, "/api/coding/context?directory=src");
  assert.deepEqual(seen[1], {
    input: "/api/coding/git/branch",
    body: { action: "switch", branch: "feature", create: true },
  });
  assert.deepEqual(seen[2], {
    input: "/api/coding/files/read",
    body: { path: "README.md" },
  });
});

test("rumi log helpers target local coding history routes", async () => {
  const seen: Array<{ input: string; method: string; body?: unknown }> = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    seen.push({
      input: String(input),
      method: init?.method ?? "GET",
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    });
    return new Response(JSON.stringify({
      status: "ok",
      data: {
        rumi_dir: "/repo/.rumi",
        events: [],
        summary: { total: 0, commit_count: 0, push_count: 0, agent_ids: [] },
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.listRumiLogs({ workspace_id: "ws1", limit: 10, kind: "git.commit" });
    await api.seedRumiLogPlan({ workspace_id: "ws1" });
    await api.appendRumiLog({ workspace_id: "ws1", kind: "agent.note", message: "watch commit pair" });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(seen[0].input, "/api/coding/rumi-log?workspace_id=ws1&limit=10&kind=git.commit");
  assert.equal(seen[0].method, "GET");
  assert.deepEqual(seen[1], {
    input: "/api/coding/rumi-log",
    method: "POST",
    body: { action: "seed_local_plan", workspace_id: "ws1" },
  });
  assert.deepEqual(seen[2], {
    input: "/api/coding/rumi-log",
    method: "POST",
    body: { action: "append", workspace_id: "ws1", kind: "agent.note", message: "watch commit pair" },
  });
});

test("listConversations serializes metadata filters", async () => {
  let requestUrl = "";
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    requestUrl = String(input);
    return new Response(JSON.stringify({
      status: "ok",
      data: { conversations: [], total: 0 },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.listConversations({
      tags: ["coding", "frontend"],
      is_pinned: true,
      company_id: "operations-company",
      workspace_id: "ws1",
      conversation_kind: "coding",
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(
    requestUrl,
    "/api/chat/conversations?tags=coding%2Cfrontend&is_pinned=true&company_id=operations-company&workspace_id=ws1&conversation_kind=coding",
  );
});

test("company and p2p helpers target frontend workspace routes", async () => {
  const seen: Array<{ input: string; method: string; body?: unknown }> = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    seen.push({
      input: path,
      method: init?.method ?? "GET",
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    });
    let data: unknown = { companies: [], total: 0 };
    if (path.includes("/p2p/status")) data = { p2p: { enabled: false }, peer_count: 0, approved_peer_count: 0 };
    if (path.includes("/p2p/messages/send")) data = { envelope: {}, peer: { peer_id: "peer-a" } };
    if (path.includes("/company/status")) data = { bootstrapped: true, company_id: "chat-team-c1", conversation_id: "c1", company: null };
    if (path.includes("/company/bootstrap")) data = { bootstrapped: true, company: { id: "chat-team-c1", name: "Executive Team" } };
    if (path.includes("/research/web-search")) data = { provider: "external_web", sources: [] };
    if (path.includes("/company/operations-company/runs")) data = { runs: [], total: 0 };
    if (path.includes("/company/operations-company/agents/reviewer/inbox")) data = { inbox: [], total: 0 };
    if (path.includes("/company/operations-company/agents") && init?.method === "POST") {
      data = { id: "reviewer", agent_id: "reviewer", model: "stub/default" };
    }
    if (path.includes("/company/operations-company/dispatch")) data = { dispatch: { status: "completed" }, run_links: [] };
    if (path.includes("/company/operations-company/tasks")) data = { id: "task-1", company_id: "operations-company", title: "Ship it" };
    return new Response(JSON.stringify({ status: "ok", data }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.listCompanies({ limit: 10 });
    await api.getCompanyStatus({ conversationId: "c1", bootstrap: true });
    await api.bootstrapCompanyWorkspace({ conversation_id: "c1", source: "webapp" }, { conversationId: "c1", scope: "conversation" });
    await api.webSearch("deep research", true);
    await api.upsertCompanyAgent("operations-company", { agent_id: "reviewer", model: "stub/default" });
    await api.createCompanyTask("operations-company", { title: "Ship it", target_agent_ids: ["reviewer"] });
    await api.dispatchCompanyTask("operations-company", "task-1");
    await api.listCompanyRuns("operations-company", { task_id: "task-1", limit: 5 });
    await api.listCompanyAgentInbox("operations-company", "reviewer", { limit: 5 });
    await api.getP2PStatus();
    await api.sendP2PMessage("peer-a", { text: "hello" });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(seen[0].input, "/api/company?limit=10");
  assert.equal(seen[1].input, "/api/company/status?conversation_id=c1&bootstrap=true");
  assert.deepEqual(seen[2], {
    input: "/api/company/bootstrap",
    method: "POST",
    body: { metadata: { conversation_id: "c1", source: "webapp" }, conversation_id: "c1", scope: "conversation" },
  });
  assert.deepEqual(seen[3], {
    input: "/api/research/web-search",
    method: "POST",
    body: { query: "deep research", allow_network: true, limit: 5 },
  });
  assert.deepEqual(seen[4], {
    input: "/api/company/operations-company/agents",
    method: "POST",
    body: {
      company_id: "operations-company",
      action: "upsert",
      agent: {
        agent_id: "reviewer",
        model: "stub/default",
      },
    },
  });
  assert.deepEqual(seen[5], {
    input: "/api/company/operations-company/tasks",
    method: "POST",
    body: {
      company_id: "operations-company",
      action: "create",
      title: "Ship it",
      target_agent_ids: ["reviewer"],
    },
  });
  assert.deepEqual(seen[6], {
    input: "/api/company/operations-company/dispatch",
    method: "POST",
    body: { company_id: "operations-company", task_id: "task-1" },
  });
  assert.equal(seen[7].input, "/api/company/operations-company/runs?company_id=operations-company&task_id=task-1&limit=5");
  assert.equal(seen[8].input, "/api/company/operations-company/agents/reviewer/inbox?company_id=operations-company&agent_id=reviewer&limit=5");
  assert.equal(seen[9].input, "/api/p2p/status");
  assert.deepEqual(seen[10], {
    input: "/api/p2p/messages/send",
    method: "POST",
    body: { peer_id: "peer-a", text: "hello" },
  });
});

test("coding workspace and compact helpers serialize request bodies", async () => {
  const seen: Array<{ input: string; method: string; body?: unknown }> = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    seen.push({
      input: String(input),
      method: init?.method ?? "GET",
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    });
    return new Response(JSON.stringify({
      status: "ok",
      data: String(input).includes("/workspaces")
        ? { workspace: { workspace_id: "ws1", label: "Repo", root_path: "/repo" }, selected_workspace_id: "ws1", workspaces: [] }
        : { deleted_count: 2, summary_message: null },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.selectCodingWorkspace("ws1");
    await api.trustCodingWorkspace("ws1");
    await api.compactConversation("c1", { protect_last_messages: 4 });
    await api.autoCompactConversation("c1", { mode: "apply", approved: true });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(seen[0], {
    input: "/api/coding/workspaces/select",
    method: "POST",
    body: { workspace_id: "ws1" },
  });
  assert.deepEqual(seen[1], {
    input: "/api/coding/workspaces/trust",
    method: "POST",
    body: { workspace_id: "ws1" },
  });
  assert.deepEqual(seen[2], {
    input: "/api/chat/conversations/c1/compact",
    method: "POST",
    body: { conversation_id: "c1", protect_last_messages: 4 },
  });
  assert.deepEqual(seen[3], {
    input: "/api/chat/conversations/c1/auto-compact",
    method: "POST",
    body: { conversation_id: "c1", mode: "apply", approved: true },
  });
});

test("directory and group storage helpers target native selection routes", async () => {
  const seen: Array<{ input: string; method: string; body?: unknown }> = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    seen.push({
      input: String(input),
      method: init?.method ?? "GET",
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    });
    return new Response(JSON.stringify({
      status: "ok",
      data: String(input).includes("/select-directory")
        ? { path: "/repo", cancelled: false }
        : { root_path: "/repo", rumi_data_path: "/repo/.rumiDP", chat_store_path: "/repo/.rumiDP/chat/conversations.json" },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.selectDirectory("保存先");
    await api.prepareChatGroupStorage("/repo");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(seen[0], {
    input: "/api/ui/select-directory",
    method: "POST",
    body: { prompt: "保存先" },
  });
  assert.deepEqual(seen[1], {
    input: "/api/chat/group-storage",
    method: "POST",
    body: { root_path: "/repo" },
  });
});
