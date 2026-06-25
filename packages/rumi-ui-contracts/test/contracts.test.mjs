import test from "node:test";
import assert from "node:assert/strict";
import {
  createRumiDataAttributes,
  defineRumiFrontend,
  normalizeRumiId,
  validateComponentContract,
  validateDesignIntent,
  validateFoundation,
  validateUINode,
} from "../src/index.mjs";

test("defineRumiFrontend locks recursive zero-to-one defaults", () => {
  const config = defineRumiFrontend({
    quality: { maxCompressionScore: 0.3 },
    viewports: [390, 768, 1440],
  });

  assert.equal(config.generation.mode, "recursive-zero-to-one");
  assert.equal(config.generation.rootMayWriteUi, false);
  assert.equal(config.quality.maxCompressionScore, 0.3);
  assert.throws(() => {
    config.quality.maxCompressionScore = 0.9;
  }, TypeError);
});

test("component contracts require bounded layout and action budget", () => {
  const contract = {
    id: "reply-composer",
    purpose: "Reply safely",
    primaryPerceptualTask: "Understand draft and send readiness",
    density: "comfortable",
    layoutEnvelope: {
      minWidth: 280,
      preferredWidth: 560,
      maxWidth: 760,
      heightBehavior: "content",
      mobileBehavior: "sticky-bottom",
    },
    inputs: ["draft", "isSending", "error"],
    events: ["onDraftChange", "onSend", "onRetry"],
    requiredStates: ["empty", "editing", "sending", "error", "sent"],
    allowedPrimitives: ["Button", "TextArea", "InlineAlert", "IconButton"],
    visibleActionBudget: 3,
  };

  assert.deepEqual(validateComponentContract(contract), []);
  assert.deepEqual(validateUINode({ id: "thread-pane", children: [{ id: "reply-composer" }] }), []);
});

test("foundation validation enforces specimen and semantic color roles", () => {
  const colorRoles = Object.fromEntries([
    "canvas",
    "surface",
    "surfaceRaised",
    "textPrimary",
    "textSecondary",
    "textMuted",
    "borderSubtle",
    "borderStrong",
    "actionPrimary",
    "actionPrimaryHover",
    "statusPositive",
    "statusWarning",
    "statusCritical",
  ].map((role) => [role, `color.${role}`]));

  const errors = validateFoundation({
    direction: { productMode: "utility" },
    typography: { body: "type.body" },
    densityProfiles: { comfortable: {}, compact: {}, dataDense: {} },
    colorRoles,
    typeSpecimen: { viewports: [390, 768, 1440] },
  });

  assert.deepEqual(errors, []);
});

test("design intent captures implementable decisions without source code", () => {
  const errors = validateDesignIntent({
    firstVisualFocus: "reply input",
    readingOrder: ["reply input", "send action"],
    visibleAtRest: ["reply input", "send action"],
    progressivelyDisclosed: ["formatting options"],
    typographyRoles: { input: "body" },
    colorRoles: { primaryAction: "action.primary" },
    spacingRelationships: [{ between: ["input", "actions"], relation: "group" }],
    overflowStrategy: "grow-until-max-then-scroll",
    mobileTransformation: "actions-remain-visible",
  });

  assert.deepEqual(errors, []);
});

test("data attributes and ids normalize to stable Rumi markers", () => {
  assert.equal(normalizeRumiId("Reply Composer"), "reply-composer");
  assert.deepEqual(createRumiDataAttributes({
    nodeId: "reply-composer",
    density: "comfortable",
    role: "interaction-region",
    source: "src/features/inbox/ReplyComposer.tsx:42",
  }), {
    "data-rumi-node": "reply-composer",
    "data-rumi-density": "comfortable",
    "data-rumi-role": "interaction-region",
    "data-rumi-source": "src/features/inbox/ReplyComposer.tsx:42",
  });
});
