import test from "node:test";
import assert from "node:assert/strict";

import {
  canExecuteComposerEndpointAction,
  composerSkillMentionDisplay,
  composerSkillMentionWidget,
  composerToolMentionDisplay,
  filterComposerSkillMentions,
  isSafeLocalEndpoint,
  skillMentionIdsFromText,
} from "./composerWidgets";

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
        syntax: "@feedback/live-review",
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

test("composer mention display prefers human labels and keeps ids visible", () => {
  assert.deepEqual(composerToolMentionDisplay({
    id: "coding_file_read",
    label: "Read File",
    category: "tool",
    description: "Read a workspace file.",
  }), {
    label: "Read File",
    description: "coding_file_read - Read a workspace file.",
  });
  assert.deepEqual(composerSkillMentionDisplay({
    id: "feedback/live-review",
    label: "Live Review",
    description: "Require evidence-backed verification.",
  }), {
    label: "Live Review",
    description: "feedback/live-review - Require evidence-backed verification.",
  });
});
