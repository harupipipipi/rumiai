import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  canExecuteComposerEndpointAction,
  composerMentionMetadataFromWidgets,
  composerFileMentionWidget,
  composerServiceMentionWidget,
  composerSkillMentionDisplay,
  composerSkillMentionWidget,
  composerToolMentionDisplay,
  composerToolMentionWidget,
  filterComposerSkillMentions,
  isSafeLocalEndpoint,
  resolveComposerWidgetDrop,
  skillMentionIdsFromText,
  toolMentionIdsFromText,
  trustedComposerActionForWidget,
} from "./composerWidgets";
import { activeMentionAtCursor, extractMentionTokens } from "./mentionContract";
import type { ComposerExtensionItem } from "../renderers/types";

type BoundaryFixture = {
  active_query: string | null;
  name: string;
  text: string;
  tokens: string[];
};

const boundaryFixtures = JSON.parse(readFileSync(resolve(
  import.meta.dirname,
  "../../../../..",
  "tests/fixtures/mention_boundaries.json",
), "utf8")) as BoundaryFixture[];

test("frontend follows the shared Unicode mention boundary fixtures", () => {
  for (const fixture of boundaryFixtures) {
    assert.deepEqual(
      extractMentionTokens(fixture.text).map((mention) => mention.value),
      fixture.tokens,
      fixture.name,
    );
    assert.equal(
      activeMentionAtCursor(fixture.text, fixture.text.length)?.query ?? null,
      fixture.active_query,
      fixture.name,
    );
  }
});

test("composer endpoint actions are limited to safe local non-approval APIs", () => {
  assert.equal(isSafeLocalEndpoint("/api/coding/git/status"), true);
  assert.equal(isSafeLocalEndpoint("//evil.example/api"), false);
  assert.equal(isSafeLocalEndpoint("https://evil.example/api"), false);
  assert.equal(isSafeLocalEndpoint("/not-api/status"), false);

  assert.equal(
    canExecuteComposerEndpointAction({
      type: "call_endpoint",
      endpoint: "/api/coding/git/status",
      requires_approval: false,
    }),
    true,
  );
  assert.equal(
    canExecuteComposerEndpointAction({
      type: "call_endpoint",
      endpoint: "/api/coding/files/write",
      requires_approval: true,
    }),
    false,
  );
  assert.equal(
    canExecuteComposerEndpointAction({
      type: "call_endpoint",
      endpoint: "/api/ui/settings",
      method: "PUT",
      requires_approval: false,
    }),
    false,
  );
});

test("composer widget drops rebuild actions from trusted catalog items", () => {
  const toolItems = [
    {
      id: "coding_git_status",
      label: "Git Status",
      category: "tool",
      ui: {
        drop_capabilities: ["composer.action_button"],
        widget_kind: "button",
        composer_label: "Git Status",
        composer_icon: "git",
        composer_action: {
          type: "call_endpoint",
          endpoint: "/api/coding/git/status",
          method: "GET",
          result_surface: "preview",
          requires_approval: false,
        },
      },
    },
  ] satisfies ComposerExtensionItem[];

  const action = resolveComposerWidgetDrop({
    id: "coding_git_status",
    sourceItemId: "coding_git_status",
    type: "button",
    label: "Forged Git",
    widgetKind: "button",
    action: {
      type: "call_endpoint",
      endpoint: "/api/ui/settings",
      method: "PUT",
      payload: { values: { yolo_mode: true } },
      requires_approval: false,
    },
  }, toolItems);

  assert.equal(action.type, "drop_widget");
  if (action.type !== "drop_widget") return;
  assert.equal(action.widget.label, "Git Status");
  assert.deepEqual(action.widget.action, toolItems[0].ui.composer_action);
  assert.equal(trustedComposerActionForWidget(action.widget, toolItems), toolItems[0].ui.composer_action);
});

test("composer skill mentions resolve aliases and create prompt widgets", () => {
  const skills = [
    {
      id: "feedback/live-review",
      label: "Live Review",
      description: "Require evidence-backed verification.",
      triggers: ["PR97_LIVE_REALITY_REVIEW"],
      appliesToTools: ["browser_use"],
      aliases: ["reality"],
    },
  ];

  assert.deepEqual(filterComposerSkillMentions(skills, "evidence").map((skill) => skill.id), ["feedback/live-review"]);
  assert.deepEqual(skillMentionIdsFromText("Use @live-review and @reality.", skills), ["feedback/live-review"]);
  assert.deepEqual(composerSkillMentionWidget(skills[0]), {
    id: "feedback/live-review",
    type: "skill",
    label: "Live Review",
    enabled: true,
    widgetKind: "skill_prompt",
    sourceItemId: "feedback/live-review",
    description: "Require evidence-backed verification.",
    metadata: {
      source: "composer_at_mention",
      mention: {
        id: "feedback/live-review",
        kind: "skill",
        label: "Live Review",
        syntax: "@Live Review",
        skill_id: "feedback/live-review",
      },
      skill: {
        id: "feedback/live-review",
        label: "Live Review",
        description: "Require evidence-backed verification.",
        triggers: ["PR97_LIVE_REALITY_REVIEW"],
        applies_to_tools: ["browser_use"],
        aliases: ["reality"],
      },
    },
  });
});

test("composer mention display keeps internal ids out of normal UI", () => {
  assert.deepEqual(composerToolMentionDisplay({
    id: "coding_file_read",
    label: "Read File",
    category: "tool",
    description: "Read a workspace file.",
  }), {
    label: "Read File",
    description: "Read a workspace file.",
  });
  assert.deepEqual(composerSkillMentionDisplay({
    id: "feedback/live-review",
    label: "Live Review",
    description: "Require evidence-backed verification.",
  }), {
    label: "Live Review",
    description: "Require evidence-backed verification.",
  });
});

test("semantic mention metadata keeps stable ids separate from human labels", () => {
  const fileWidget = composerFileMentionWidget("src/App.tsx");
  const serviceWidget = composerServiceMentionWidget({
    id: "github",
    label: "GitHub",
    toolIds: ["github_issue_search"],
  });
  assert.deepEqual(composerMentionMetadataFromWidgets([fileWidget, serviceWidget]), [
    {
      id: "src/App.tsx",
      kind: "file",
      label: "src/App.tsx",
      syntax: "@src/App.tsx",
    },
    {
      id: "github",
      kind: "service",
      label: "GitHub",
      syntax: "@GitHub",
    },
  ]);
});

test("duplicate human labels are not ambiguously reparsed", () => {
  const tools = [
    { id: "browser_computer", label: "Browser", category: "tool" },
    { id: "browser_companion", label: "Browser", category: "tool" },
  ];
  assert.deepEqual(skillMentionIdsFromText("@Browser", []), []);
  assert.deepEqual(toolMentionIdsFromText("@Browser", tools), []);
  assert.deepEqual(toolMentionIdsFromText("@browser_computer", tools), ["browser_computer"]);
  assert.deepEqual(composerMentionMetadataFromWidgets([
    composerToolMentionWidget(tools[1]),
  ]), [{
    id: "browser_companion",
    kind: "tool",
    label: "Browser",
    syntax: "@Browser",
  }]);
});

test("copy and paste keeps human mention text literal without exposing an internal id", () => {
  const tools = [{ id: "browser_computer", label: "Browser Computer", category: "tool" }];
  const pastedText = "Use @Browser Computer";

  assert.equal(pastedText.includes("browser_computer"), false);
  assert.deepEqual(toolMentionIdsFromText(pastedText, tools), []);
});
