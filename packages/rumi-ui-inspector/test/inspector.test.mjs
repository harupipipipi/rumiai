import test from "node:test";
import assert from "node:assert/strict";
import {
  calculateCompressionScore,
  gapPressure,
  hardGateViolations,
  inspectCandidate,
  inspectColorUsage,
} from "../src/index.mjs";
import { defineRumiFrontend } from "../../rumi-ui-contracts/src/index.mjs";

test("gap pressure flags gaps below 75 percent of foundation spacing", () => {
  assert.equal(gapPressure([{ actual: 5, expected: 8 }]), 0.167);
  assert.equal(gapPressure([{ actual: 6, expected: 8 }]), 0);
});

test("hard gates reject truncation, overflow, action over-budget, and padding violations", () => {
  const violations = hardGateViolations({
    primaryContentClipped: true,
    horizontalOverflow: true,
    actions: { visibleCount: 4 },
    regions: [{ id: "reply", actualPadding: 8, requiredPadding: 12 }],
  }, {
    id: "reply-composer",
    density: "comfortable",
    visibleActionBudget: 3,
  });

  assert.deepEqual(violations.map((violation) => violation.id), [
    "primary-content-clipped",
    "horizontal-overflow",
    "visible-action-budget-exceeded",
    "region-padding-violation",
  ]);
});

test("compression score uses weighted pressure model", () => {
  assert.equal(calculateCompressionScore({
    gapPressure: 0.4,
    textPressure: 0.2,
    actionPressure: 0,
    boundaryPressure: 0.2,
    surfacePressure: 0.1,
    hierarchyFlattening: 0.5,
  }), 0.255);
});

test("inspector passes only candidates below score and without hard gates", () => {
  const result = inspectCandidate({
    candidateId: "a",
    gaps: [{ actual: 8, expected: 8 }],
    text: { samples: [{ lineHeightRatio: 1.4 }] },
    actions: { visibleCount: 2 },
    regions: [{ actualPadding: 16, requiredPadding: 12 }],
    surfaces: {},
    hierarchy: [],
  }, {
    id: "reply-composer",
    density: "comfortable",
    visibleActionBudget: 3,
  }, defineRumiFrontend());

  assert.equal(result.passed, true);
  assert.equal(result.compressionScore, 0);
});

test("color inspection rejects arbitrary hex and status misuse", () => {
  const violations = inspectColorUsage({
    accentColorCoverage: 0.2,
    styles: [
      { value: "#ff00aa", source: "Button.css:3" },
      { value: "var(--color-status-critical)", token: "color.statusCritical", semanticRole: "statusCritical", intent: "accent" },
      { value: "var(--color-action-primary)", stateEncodedByColorOnly: true },
    ],
  }, {
    colorRoles: { actionPrimary: "color.actionPrimary", statusCritical: "color.statusCritical" },
  });

  assert.deepEqual(violations.map((violation) => violation.id), [
    "arbitrary-hex-color",
    "status-color-misuse",
    "color-only-state",
    "accent-color-overuse",
  ]);
});
