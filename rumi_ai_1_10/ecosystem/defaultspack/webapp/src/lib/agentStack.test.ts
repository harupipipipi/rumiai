import test from "node:test";
import assert from "node:assert/strict";

import {
  agentStackProfileAvailability,
  applyAgentStackToolOverrides,
  batchAgentStackToolOverrides,
  buildAgentStackConversationStateForStorage,
  mergeAgentStackProfiles,
  normalizeAgentStackSettings,
  resolveAgentStackProfiles,
  resolveAgentStackSelection,
  toggleAgentStackToolOverride,
} from "./agentStack";

test("normalizeAgentStackSettings falls back to built-ins when JSON is invalid", () => {
  const settings = normalizeAgentStackSettings({
    profiles_json: "{not json",
    default_profile_ids: ["coding", "missing"],
  });

  assert.equal(settings.parseError !== null, true);
  assert.deepEqual(settings.defaultProfileIds, ["coding"]);
  assert.deepEqual(settings.profiles.map((profile) => profile.id), ["coding", "subagent", "all", "yolo"]);
});

test("resolveAgentStackSelection prefers conversation overrides over group defaults", () => {
  const settings = normalizeAgentStackSettings({
    default_profile_ids: ["all"],
    group_defaults: { "group/coding": ["coding"] },
  });

  const selection = resolveAgentStackSelection({
    settings,
    groupId: "group/coding",
    conversationState: {
      profile_ids: ["yolo"],
      tool_overrides: { browser_use: true },
    },
  });

  assert.equal(selection.source, "conversation");
  assert.deepEqual(selection.defaultProfileIds, ["coding"]);
  assert.deepEqual(selection.profileIds, ["yolo"]);
  assert.deepEqual(selection.toolOverrides, { browser_use: true });
});

test("agentStackProfileAvailability supports vision and model id constraints", () => {
  const [coding, subagent, all, yolo] = normalizeAgentStackSettings({}).profiles;
  const deepseekVision = {
    ...coding,
    constraints: {
      requires_vision: true,
      model_id_includes: ["deepseek"],
    },
  };

  assert.deepEqual(
    agentStackProfileAvailability(deepseekVision, {
      profile_id: "deepseek-vision",
      display_name: "DeepSeek Vision",
      provider_id: "opencode-zen",
      model_id: "deepseek-vl",
      supports_vision: true,
    }),
    { matches: true, reason: null },
  );
  assert.equal(
    agentStackProfileAvailability({ ...all, constraints: { requires_vision: true } }, {
      profile_id: "text-only",
      display_name: "Text Only",
      provider_id: "stub",
      model_id: "default",
      supports_vision: false,
    }).matches,
    false,
  );
  assert.equal(
    agentStackProfileAvailability({ ...yolo, constraints: { model_id_includes: ["deepseek"] } }, {
      profile_id: "gemini",
      display_name: "Gemini",
      provider_id: "google",
      model_id: "gemini-2.5-pro",
      supports_vision: true,
    }).matches,
    false,
  );
  assert.deepEqual(
    agentStackProfileAvailability(subagent, {
      profile_id: "opencode-zen/minimax-m3-free",
      qualified_model_id: "opencode-zen/minimax-m3-free",
      display_name: "MiniMax M3 Free via OpenCode Zen",
      provider_id: "opencode-zen",
      model_id: "minimax-m3-free",
      supports_vision: true,
    }),
    { matches: true, reason: null },
  );
  assert.equal(
    agentStackProfileAvailability(subagent, {
      profile_id: "openai/gpt-5.4",
      display_name: "GPT-5.4",
      provider_id: "openai",
      model_id: "gpt-5.4",
      supports_vision: true,
    }).matches,
    false,
  );
});

test("mergeAgentStackProfiles unions tools and skills and concatenates prompts", () => {
  const merged = mergeAgentStackProfiles([
    {
      id: "one",
      label: "One",
      tools: ["coding_file_read", "coding_git_diff"],
      skills: ["skill.a"],
      system_prompt: "Prompt A",
      tool_policy: { allow_shell: true, model_allowlist: ["deepseek/deepseek-chat"] },
    },
    {
      id: "two",
      label: "Two",
      tools: ["coding_git_diff", "browser_use"],
      skills: ["skill.b", "skill.a"],
      system_prompt: "Prompt B",
      tool_policy: { allow_file_write: true, model_allowlist: ["google/gemini-2.5-pro"] },
    },
  ]);

  assert.deepEqual(merged.toolIds, ["coding_file_read", "coding_git_diff", "browser_use"]);
  assert.deepEqual(merged.skillIds, ["skill.a", "skill.b"]);
  assert.equal(merged.systemPrompt, "Prompt A\n\nPrompt B");
  assert.deepEqual(merged.toolPolicy, {
    allow_shell: true,
    allow_file_write: true,
    model_allowlist: ["deepseek/deepseek-chat", "google/gemini-2.5-pro"],
  });
});

test("tool overrides let sidebar changes win until profiles are switched again", () => {
  const baseToolIds = ["coding_file_read", "browser_use"];
  const toggledOff = toggleAgentStackToolOverride(baseToolIds, {}, "browser_use", false);
  const toggledOn = toggleAgentStackToolOverride(baseToolIds, toggledOff, "coding_terminal_exec", true);
  const finalTools = applyAgentStackToolOverrides(baseToolIds, toggledOn);

  assert.deepEqual(toggledOn, {
    browser_use: false,
    coding_terminal_exec: true,
  });
  assert.deepEqual(finalTools, ["coding_file_read", "coding_terminal_exec"]);
});

test("batchAgentStackToolOverrides toggles many tools and storage clears when state matches defaults", () => {
  const baseToolIds = ["coding_file_read"];
  const overrides = batchAgentStackToolOverrides(baseToolIds, {}, ["coding_terminal_exec", "browser_use"], true);
  const storageState = buildAgentStackConversationStateForStorage(["coding"], ["coding"], overrides);
  const clearedState = buildAgentStackConversationStateForStorage(["coding"], ["coding"], {});

  assert.deepEqual(overrides, {
    coding_terminal_exec: true,
    browser_use: true,
  });
  assert.deepEqual(storageState, {
    profile_ids: ["coding"],
    tool_overrides: {
      coding_terminal_exec: true,
      browser_use: true,
    },
  });
  assert.equal(clearedState, null);
});

test("resolveAgentStackProfiles keeps selected but unavailable profiles visible", () => {
  const settings = normalizeAgentStackSettings({
    profiles_json: JSON.stringify([
      {
        id: "vision-deepseek",
        label: "vision-deepseek",
        constraints: { requires_vision: true, model_id_includes: ["deepseek"] },
      },
      {
        id: "plain",
        label: "plain",
      },
    ]),
  });

  const resolved = resolveAgentStackProfiles(["vision-deepseek", "plain"], settings, {
    profile_id: "google/gemini-2.5-pro",
    display_name: "Gemini 2.5 Pro",
    provider_id: "google",
    model_id: "gemini-2.5-pro",
    supports_vision: true,
  });

  assert.equal(resolved[0]?.available, false);
  assert.equal(resolved[1]?.available, true);
});
