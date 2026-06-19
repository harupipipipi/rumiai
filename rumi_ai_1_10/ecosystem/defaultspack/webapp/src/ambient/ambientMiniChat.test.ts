import assert from "node:assert/strict";
import test from "node:test";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { Conversation } from "../lib/api";
import { AUTHORITY_FOLLOWUP_TEXT, AUTHORITY_WAITING_TEXT } from "../lib/authorityApproval";
import { buildAmbientDispatchTemplateContext, mergeAmbientDispatchMetadata } from "./ambientDispatchContext";
import { AmbientMiniChat } from "./AmbientMiniChat";
import {
  ambientConversationIdFromResult,
  ambientLatestAssistantFinalText,
  ambientLinkedConversationId,
  ambientMiniChatMessages,
  ambientPendingAuthorityApproval,
} from "./ambientMiniChatState";
import { ambientSelectedModelDisplay, ambientVisibleModelOptions } from "./ambientRouting";
import type { AmbientStatus } from "./ambientTriggerClient";

test("ambient mini chat resolves the linked conversation from routing state", () => {
  assert.equal(ambientLinkedConversationId(status({ mode: "selected_chat", conversation_id: "chat-1" }), null), "chat-1");
  assert.equal(ambientLinkedConversationId(status({ mode: "selected_chat" }), "active-chat"), "active-chat");
  assert.equal(ambientLinkedConversationId(status({ mode: "startup_new_chat", session_conversation_id: "session-chat" }), "active-chat"), "session-chat");
  assert.equal(ambientLinkedConversationId(status({ mode: "always_new_chat", conversation_id: "ignored" }), "active-chat"), null);
});

test("ambient mini chat extracts dispatched conversation ids from ambient results", () => {
  assert.equal(ambientConversationIdFromResult({ conversation_id: "top-level" }), "top-level");
  assert.equal(ambientConversationIdFromResult({ dispatch: { conversation_id: "dispatch-chat" } }), "dispatch-chat");
  assert.equal(ambientConversationIdFromResult({ pending_approval: { conversation_id: "pending-chat" } }), "pending-chat");
  assert.equal(ambientConversationIdFromResult({ status: "ok" }), null);
});

test("ambient mini chat keeps recent user and assistant text in order", () => {
  const conversation = {
    id: "c1",
    title: "Mini",
    created_at: 1,
    updated_at: 4,
    model: "stub/default",
    tags: [],
    is_starred: false,
    is_archived: false,
    messages: [
      message({ id: "a1", role: "assistant", raw_text: "こんにちは", created_at: 3, sequence_number: 2 }),
      message({ id: "u1", role: "user", raw_text: "hello こんにちは", created_at: 2, sequence_number: 1 }),
      message({ id: "s1", role: "system", raw_text: "hidden", created_at: 1, sequence_number: 0 }),
    ],
  } satisfies Conversation;

  assert.deepEqual(ambientMiniChatMessages(conversation, 4), [
    { id: "u1", role: "user", text: "hello こんにちは", createdAt: 2 },
    { id: "a1", role: "assistant", text: "こんにちは", createdAt: 3 },
  ]);
});

test("ambient mini chat detects pending authority and hides the approval placeholder", () => {
  const conversation = conversationWithMessages([
    message({ id: "u1", role: "user", raw_text: "I'll see you next time.", created_at: 2, sequence_number: 1 }),
    message({
      id: "a1",
      role: "assistant",
      raw_text: AUTHORITY_WAITING_TEXT,
      content: [{ type: "text", text: AUTHORITY_WAITING_TEXT }],
      created_at: 3,
      sequence_number: 2,
      metadata: {
        pendingAuthorityApproval: {
          request_id: "auth-1",
          principal_id: "local-user",
          permission_id: "model.invoke",
          resource: { provider_id: "opencode-go", model_id: "deepseek-v4-flash" },
        },
      },
    }),
  ]);

  const approval = ambientPendingAuthorityApproval(conversation);
  assert.equal(approval?.requestId, "auth-1");
  assert.deepEqual(ambientMiniChatMessages(conversation, 4), [
    { id: "u1", role: "user", text: "I'll see you next time.", createdAt: 2 },
  ]);
  assert.equal(ambientLatestAssistantFinalText(conversation), null);
});

test("ambient mini chat detects approval_requested events and renders a compact authority CTA", () => {
  const conversation = conversationWithMessages([
    message({ id: "u1", role: "user", raw_text: "hello", created_at: 2, sequence_number: 1 }),
    message({
      id: "a1",
      role: "assistant",
      raw_text: AUTHORITY_WAITING_TEXT,
      content: [{ type: "text", text: AUTHORITY_WAITING_TEXT }],
      created_at: 3,
      sequence_number: 2,
      events: [{
        type: "approval_requested",
        request_id: "auth-event-1",
        principal_id: "local-user",
        permission_id: "model.invoke",
        authority: true,
        resource: { provider_id: "opencode-go" },
      }],
    }),
  ]);
  const approval = ambientPendingAuthorityApproval(conversation);
  assert.equal(approval?.requestId, "auth-event-1");

  const html = renderToStaticMarkup(createElement(AmbientMiniChat, {
    conversation,
    conversationId: "c1",
    routingSummary: "Mini",
    loading: false,
    error: null,
    input: "",
    sending: false,
    disabled: true,
    latestInputPreview: null,
    authorityApproval: approval,
    onInputChange: () => {},
    onSubmit: (event) => event.preventDefault(),
    onRefresh: () => {},
    onPickChat: () => {},
    onOpenAuthorityApproval: () => {},
  }));

  assert.match(html, /AIの使用を許可/);
  assert.match(html, /承認を開く/);
  assert.equal(html.includes(AUTHORITY_WAITING_TEXT), false);
});

test("ambient mini chat renders browser token prompt instead of approval CTA when token is required", () => {
  const approval = {
    requestId: "auth-browser-1",
    principalId: "local-user",
    permissionId: "model.invoke",
    resource: {},
  };
  const html = renderToStaticMarkup(createElement(AmbientMiniChat, {
    conversation: null,
    conversationId: "c1",
    routingSummary: "Mini",
    loading: false,
    error: null,
    input: "",
    sending: false,
    disabled: true,
    latestInputPreview: null,
    authorityApproval: approval,
    browserApprovalTokenPrompt: {
      required: true,
      token: "",
      onTokenChange: () => {},
      onSave: () => {},
    },
    onInputChange: () => {},
    onSubmit: (event) => event.preventDefault(),
    onRefresh: () => {},
    onPickChat: () => {},
    onOpenAuthorityApproval: () => {},
  }));

  assert.match(html, /ブラウザで承認するにはテストトークンが必要です/);
  assert.match(html, /browser_approval_token/);
  assert.match(html, /保存/);
  assert.equal(html.includes("承認を開く"), false);
});

test("ambient mini chat hides hidden authority resume and keeps only the final answer for readout", () => {
  const conversation = conversationWithMessages([
    message({ id: "u1", role: "user", raw_text: "question", created_at: 2, sequence_number: 1 }),
    message({
      id: "a1",
      role: "assistant",
      raw_text: AUTHORITY_WAITING_TEXT,
      content: [{ type: "text", text: AUTHORITY_WAITING_TEXT }],
      created_at: 3,
      sequence_number: 2,
      metadata: {
        pendingAuthorityApproval: {
          request_id: "auth-2",
          permission_id: "model.invoke",
          resource: {},
        },
      },
    }),
    message({
      id: "u2",
      role: "user",
      raw_text: AUTHORITY_FOLLOWUP_TEXT,
      content: [{ type: "text", text: AUTHORITY_FOLLOWUP_TEXT }],
      created_at: 4,
      sequence_number: 3,
      metadata: {
        authority_followup: {
          request_id: "auth-2",
          permission_id: "model.invoke",
        },
        chat_display: {
          hidden: true,
          reason: "authority_followup",
        },
      },
    }),
    message({ id: "a2", role: "assistant", raw_text: "また会いましょう。", created_at: 5, sequence_number: 4 }),
  ]);

  const miniMessages = ambientMiniChatMessages(conversation, 6);
  assert.deepEqual(miniMessages, [
    { id: "u1", role: "user", text: "question", createdAt: 2 },
    { id: "a2", role: "assistant", text: "また会いましょう。", createdAt: 5 },
  ]);
  assert.equal(miniMessages.some((item) => item.text === AUTHORITY_FOLLOWUP_TEXT), false);
  assert.equal(ambientPendingAuthorityApproval(conversation), null);
  assert.equal(ambientLatestAssistantFinalText(conversation), "また会いましょう。");
});

test("ambient mini chat hides routing picker controls for the standalone normal screen", () => {
  const html = renderToStaticMarkup(createElement(AmbientMiniChat, {
    conversation: null,
    conversationId: null,
    routingSummary: "次の送信で作成",
    loading: false,
    error: null,
    input: "",
    sending: false,
    disabled: false,
    latestInputPreview: null,
    showPicker: false,
    onInputChange: () => {},
    onSubmit: (event) => event.preventDefault(),
    onRefresh: () => {},
    onPickChat: () => {},
  }));

  assert.equal(html.includes("チャットを選ぶ"), false);
  assert.equal(html.includes("選択"), false);
  assert.equal(html.includes("Defaultspack"), false);
  assert.match(html, /次の送信で作成/);
  assert.match(html, /メッセージ/);
});

test("ambient compact routing model options use template modelSelect display shape", () => {
  const models = [
    {
      profile_id: "google/gemini-2.5-flash",
      display_name: "Gemini 2.5 Flash",
      provider_id: "google",
      provider_display_name: "Google",
      model_id: "gemini-2.5-flash",
      api_key_configured: true,
      supports_tool_calling: true,
    },
    {
      profile_id: "openai/gpt-4.1",
      display_name: "GPT 4.1",
      provider_id: "openai",
      provider_display_name: "OpenAI",
      model_id: "gpt-4.1",
      requires_api_key: true,
      api_key_configured: false,
    },
  ];

  const selected = ambientSelectedModelDisplay("google/gemini-2.5-flash", models);
  assert.equal(selected?.label, "Gemini 2.5 Flash");
  assert.deepEqual(selected?.badges.map((badge) => badge.id), ["configured", "tools"]);

  const visible = ambientVisibleModelOptions({
    model: "google/gemini-2.5-flash",
    modelQuery: "api key",
    modelResults: models,
    limit: 6,
  });
  assert.deepEqual(visible.map((option) => option.value), [
    "google/gemini-2.5-flash",
    "openai/gpt-4.1",
  ]);
});

test("ambient dispatch context carries template model and selected tool policy metadata", () => {
  const context = buildAmbientDispatchTemplateContext({
    model: "google/gemini-2.5-flash",
    templateParams: { max_output_tokens: 2048 },
    templateToolPolicy: { policy_id: "template.default" },
    selectedToolIds: ["local_file", "browser", "local_file", ""],
  });

  assert.deepEqual(context.eventPayload, {
    model: "google/gemini-2.5-flash",
    params: {
      max_output_tokens: 2048,
      model: "google/gemini-2.5-flash",
      tool_selection: {
        mode: "manual",
        include: ["local_file", "browser"],
        scope: "turn",
        must_use: false,
      },
      tool_policy: {
        policy_id: "template.default",
        selected_tools: ["local_file", "browser"],
      },
    },
    tools: ["local_file", "browser"],
  });
  assert.deepEqual(mergeAmbientDispatchMetadata({ panel: "ambient_mini_window" }, context), {
    panel: "ambient_mini_window",
    selected_model: "google/gemini-2.5-flash",
    selected_tools: ["local_file", "browser"],
    tool_selection_scope: "turn",
  });
});

function status(routing: AmbientStatus["routing"]): AmbientStatus {
  return {
    ambient_monitor: { enabled: false },
    services: {
      voice_wake_monitor: {},
      gesture_wake_monitor: {},
    },
    permissions: {
      rumi: {},
      os: {},
    },
    routing,
  };
}

function conversationWithMessages(messages: Conversation["messages"]): Conversation {
  return {
    id: "c1",
    title: "Mini",
    created_at: 1,
    updated_at: 5,
    model: "stub/default",
    tags: [],
    is_starred: false,
    is_archived: false,
    messages,
  };
}

function message(patch: Partial<Conversation["messages"][number]>): Conversation["messages"][number] {
  return {
    id: "m",
    role: "user",
    content: [{ type: "text", text: "" }],
    raw_text: "",
    created_at: 1,
    conversation_id: "c1",
    ...patch,
  };
}
