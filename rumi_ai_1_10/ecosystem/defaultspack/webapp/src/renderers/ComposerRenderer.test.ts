import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { CodingWorkspacePicker } from "../components/coding/CodingWorkspacePicker";
import {
  filterAtMentionFiles,
  insertAtMentionText,
  modelCandidateMenuKeyAction,
  nextModelCandidateIndex,
  profileNeedsApiKey,
  ComposerRenderer,
  resolveComposerWidgetDrop,
  shouldFocusComposerForSlashKey,
} from "./ComposerRenderer";
import { COMPOSER_BUTTON_DROP, COMPOSER_PANEL_DROP, COMPOSER_SELECTOR_DROP, COMPOSER_TOGGLE_DROP } from "../lib/toolUi";

test("composer file mention filters string context files", () => {
  const files = ["README.md", "src/App.tsx", "docs/context.md"];

  assert.deepEqual(filterAtMentionFiles(files, "md"), ["README.md", "docs/context.md"]);
  assert.equal(typeof filterAtMentionFiles(files, "")[0], "string");
});

test("composer file mention insertion keeps @ text for workspace attachment flow", () => {
  const result = insertAtMentionText("please @REA now", 11, "README.md");

  assert.deepEqual(result, {
    value: "please @README.md  now",
    cursor: 18,
  });
});

test("model candidate menu keyboard helpers cycle and select", () => {
  assert.equal(nextModelCandidateIndex(0, 3, 1), 1);
  assert.equal(nextModelCandidateIndex(2, 3, 1), 0);
  assert.equal(nextModelCandidateIndex(0, 3, -1), 2);
  assert.equal(nextModelCandidateIndex(2, 3, -1), 1);
  assert.equal(nextModelCandidateIndex(0, 0, 1), 0);

  assert.deepEqual(modelCandidateMenuKeyAction("Tab", false, 0, 3), {
    handled: true,
    type: "move",
    nextIndex: 1,
  });
  assert.deepEqual(modelCandidateMenuKeyAction("Tab", true, 0, 3), {
    handled: true,
    type: "move",
    nextIndex: 2,
  });
  assert.deepEqual(modelCandidateMenuKeyAction("ArrowDown", false, 1, 3), {
    handled: true,
    type: "move",
    nextIndex: 2,
  });
  assert.deepEqual(modelCandidateMenuKeyAction("ArrowUp", false, 1, 3), {
    handled: true,
    type: "move",
    nextIndex: 0,
  });
  assert.deepEqual(modelCandidateMenuKeyAction("Enter", false, 9, 3), {
    handled: true,
    type: "select",
    index: 2,
  });
  assert.deepEqual(modelCandidateMenuKeyAction("Escape", false, 1, 3), {
    handled: true,
    type: "close",
  });
  assert.deepEqual(modelCandidateMenuKeyAction("Home", false, 1, 3), { handled: false });
  assert.deepEqual(modelCandidateMenuKeyAction("Tab", false, 0, 0), { handled: false });
  assert.deepEqual(modelCandidateMenuKeyAction("Enter", false, 0, 0), { handled: false });
  assert.deepEqual(modelCandidateMenuKeyAction("Escape", false, 0, 0), { handled: false });
});

test("slash key focuses composer only for plain document shortcuts", () => {
  const base = {
    key: "/",
    metaKey: false,
    ctrlKey: false,
    altKey: false,
    defaultPrevented: false,
    isComposing: false,
  };

  assert.equal(shouldFocusComposerForSlashKey(base, null), true);
  assert.equal(shouldFocusComposerForSlashKey({ ...base, key: "a" }, null), false);
  assert.equal(shouldFocusComposerForSlashKey({ ...base, metaKey: true }, null), false);
  assert.equal(shouldFocusComposerForSlashKey({ ...base, defaultPrevented: true }, null), false);
});

test("composer model drop selects the model instead of creating a widget chip", () => {
  const action = resolveComposerWidgetDrop(
    { id: "openai/gpt-4.1", type: "model", label: "GPT 4.1" },
    [],
  );

  assert.deepEqual(action, { type: "select_model", profileId: "openai/gpt-4.1" });
});

test("composer uses the main input as steer while generating", () => {
  const html = renderToStaticMarkup(
    createElement(ComposerRenderer, {
      input: "次は短くして",
      placeholder: "メッセージを入力...",
      isGenerating: true,
      selectedProfile: {
        profile_id: "stub/default",
        display_name: "Stub Default",
        provider_id: "stub",
        model_id: "default",
      },
      favoriteProfiles: [],
      inlineExtensions: [],
      belowExtensions: [],
      thinkingLevel: null,
      contextUsage: { ratio: 0, usedTokens: 0, maxContext: 0, label: "0%" },
      onInputChange: () => undefined,
      onSubmit: () => undefined,
      onModelProfileSelect: () => undefined,
      onThinkingLevelChange: () => undefined,
      onSteerSubmit: () => undefined,
    }),
  );

  assert.match(html, /実行中のAIへステアを入力/);
  assert.match(html, /Enterでステアを送信/);
  assert.match(html, /title="ステアを送る"/);
  assert.doesNotMatch(html, /textarea[^>]*disabled/);
  assert.doesNotMatch(html, /これがステア/);
  assert.doesNotMatch(html, /フォローアップの変更を求める/);
});

test("composer asks for an API key when an unconfigured Gemini model is selected", () => {
  assert.equal(profileNeedsApiKey({
    profile_id: "google/gemini-2.5-flash",
    display_name: "Gemini 2.5 Flash",
    provider_id: "google",
    model_id: "gemini-2.5-flash",
    availability: { configured: false, status: "catalog" },
  }), true);

  assert.equal(profileNeedsApiKey({
    profile_id: "google/gemma-4-26b-a4b-it",
    display_name: "Gemma 4 26B A4B IT",
    provider_id: "google",
    model_id: "gemma-4-26b-a4b-it",
    availability: { configured: false, status: "catalog" },
  }), true);

  assert.equal(profileNeedsApiKey({
    profile_id: "google/gemini-2.5-flash",
    display_name: "Gemini 2.5 Flash",
    provider_id: "google",
    model_id: "gemini-2.5-flash",
    availability: { configured: true, status: "configured" },
  }), false);

  assert.equal(profileNeedsApiKey({
    profile_id: "openai/gpt-5.4",
    display_name: "GPT-5.4",
    provider_id: "openai",
    model_id: "gpt-5.4",
    availability: { configured: false, status: "catalog" },
  }), true);

  assert.equal(profileNeedsApiKey({
    profile_id: "stub/default",
    display_name: "Stub Default",
    provider_id: "stub",
    model_id: "default",
  }), false);

  assert.equal(profileNeedsApiKey({
    profile_id: "ollama/llama3.2",
    display_name: "Llama 3.2",
    provider_id: "ollama",
    model_id: "llama3.2",
    availability: { configured: false, local: true, status: "catalog" },
  }), false);
});

test("composer widget drop requires explicit kind capability contract", () => {
  const toolItems = [
    {
      id: "coding_file_read",
      label: "Read File",
      ui: { widget_kind: "tool_toggle", drop_capabilities: [COMPOSER_TOGGLE_DROP] },
    },
    {
      id: "git_status",
      label: "Git Status",
      ui: { widget_kind: "button", drop_capabilities: [COMPOSER_BUTTON_DROP] },
    },
    {
      id: "provider-catalog",
      label: "Providers",
      ui: { widget_kind: "panel", drop_capabilities: [COMPOSER_PANEL_DROP] },
    },
    {
      id: "model-selector",
      label: "Model Selector",
      ui: { widget_kind: "selector", drop_capabilities: [COMPOSER_SELECTOR_DROP] },
    },
    {
      id: "bad-panel",
      label: "Bad Panel",
      ui: { widget_kind: "panel", drop_capabilities: [COMPOSER_TOGGLE_DROP] },
    },
  ];

  assert.equal(resolveComposerWidgetDrop({ id: "coding_file_read", type: "tool", label: "Read" }, toolItems).type, "drop_widget");
  assert.equal(resolveComposerWidgetDrop({ id: "git_status", type: "button", label: "Git", widgetKind: "button" }, toolItems).type, "drop_widget");
  assert.equal(resolveComposerWidgetDrop({ id: "provider-catalog", type: "panel", label: "Providers", widgetKind: "panel" }, toolItems).type, "drop_widget");
  assert.equal(resolveComposerWidgetDrop({ id: "model-selector", type: "selector", label: "Models", widgetKind: "selector" }, toolItems).type, "drop_widget");
  assert.equal(resolveComposerWidgetDrop({ id: "bad-panel", type: "panel", label: "Bad", widgetKind: "panel" }, toolItems).type, "ignore");
  assert.equal(resolveComposerWidgetDrop({ id: "unknown", type: "button", label: "Unknown" }, toolItems).type, "ignore");
});

test("coding workspace picker renders selected workspace and trust affordance", () => {
  const html = renderToStaticMarkup(
    createElement(CodingWorkspacePicker, {
      workspaces: [
        { workspace_id: "ws1", label: "Main Repo", root_path: "/repo", trusted: false },
      ],
      selectedWorkspaceId: "ws1",
      onSelect: () => undefined,
      onTrust: () => undefined,
      onRefresh: () => undefined,
    }),
  );

  assert.match(html, /Main Repo/);
  assert.match(html, /Trust workspace/);
});
