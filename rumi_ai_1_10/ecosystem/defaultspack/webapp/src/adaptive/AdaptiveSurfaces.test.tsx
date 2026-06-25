import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { ActivityCenter } from "./ActivityCenter";
import { AutomationStudio } from "./AutomationStudio";
import { ContextBudgetPanel, EvidenceViewer, RepositoryMapPanel } from "./EvidencePanels";
import { OnboardingShell } from "./OnboardingShell";
import { OperatingProfilePage } from "./OperatingProfilePage";

test("OnboardingShell renders the adaptive setup steps", () => {
  const html = renderToStaticMarkup(createElement(OnboardingShell));

  assert.match(html, /Onboarding/);
  assert.match(html, /Use cases/);
  assert.match(html, /Privacy and memory/);
  assert.match(html, /Settings diff/);
});

test("OperatingProfilePage renders profile controls and guardrails", () => {
  const html = renderToStaticMarkup(createElement(OperatingProfilePage));

  assert.match(html, /Operating Profile/);
  assert.match(html, /Profile summary/);
  assert.match(html, /Autonomy mode/);
  assert.match(html, /Approval policy/);
});

test("ActivityCenter renders activity counters and review queue", () => {
  const html = renderToStaticMarkup(createElement(ActivityCenter));

  assert.match(html, /Activity Center/);
  assert.match(html, /Running/);
  assert.match(html, /Needs review/);
  assert.match(html, /Review queue/);
});

test("AutomationStudio renders automations, templates, and simulation", () => {
  const html = renderToStaticMarkup(createElement(AutomationStudio));

  assert.match(html, /Automation Studio/);
  assert.match(html, /Daily context refresh/);
  assert.match(html, /Simulation/);
  assert.match(html, /Templates/);
});

test("evidence, repository, and budget panels render compact degraded surfaces", () => {
  const html = [
    renderToStaticMarkup(createElement(EvidenceViewer)),
    renderToStaticMarkup(createElement(RepositoryMapPanel)),
    renderToStaticMarkup(createElement(ContextBudgetPanel)),
  ].join("\n");

  assert.match(html, /Evidence Viewer/);
  assert.match(html, /Repository Map/);
  assert.match(html, /Context Budget/);
});
