import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  UiPrecisionComparator,
  compressionDelta,
  gateSummary,
  promptFingerprint,
  proofForViewport,
  uiPrecisionScenarioLibrary,
} from "./UiPrecisionComparator";
import type { PrecisionViewport } from "./UiPrecisionComparator";

type ComparatorLeaf = Parameters<typeof compressionDelta>[0];
type ComparatorGate = Parameters<typeof gateSummary>[0][number];
type ComparatorProof = NonNullable<Parameters<typeof proofForViewport>[1]>[number];

type AdvancedComparatorCase = {
  name: string;
  leaf: ComparatorLeaf;
  gates: ComparatorGate[];
  proofs: ComparatorProof[];
  selectedViewport: PrecisionViewport;
  expectedDelta: number;
  expectedRawFailed: number;
  expectedSelectedProof: string;
};

const advancedComparatorCases: AdvancedComparatorCase[] = [
  {
    name: "AI chat app with nested tool and source surfaces",
    leaf: {
      id: "chat-nested-surfaces",
      label: "ChatNestedSurfaces",
      purpose: "messages, citations, tool calls, composer pressure",
      status: "accepted",
      rawCompression: 0.69,
      rumiCompression: 0.21,
      rawActions: 14,
      rumiActions: 4,
      candidates: 3,
      acceptedCandidate: "C",
    },
    gates: [
      { id: "source-stack", label: "Source stack stays readable", raw: "fail", rumi: "pass", detail: "raw output compresses citations into message bubbles" },
      { id: "tool-state", label: "Tool loading and error state", raw: "fail", rumi: "pass", detail: "rumi separates running, failed, and empty tool states" },
      { id: "composer-budget", label: "Composer action budget", raw: "warn", rumi: "pass", detail: "raw toolbar exceeds mobile action budget" },
    ],
    proofs: [
      {
        viewport: 390,
        label: "mobile chat stress route",
        rawIssues: "tool cards and source chips collide with the composer",
        rumiIssues: "chat, tools, and sources become route-level surfaces",
        rawScore: 0.72,
        rumiScore: 0.24,
      },
      {
        viewport: 768,
        label: "tablet chat drawer",
        rawIssues: "source drawer hides running tool state",
        rumiIssues: "tool state remains visible beside source proof",
        rawScore: 0.55,
        rumiScore: 0.2,
      },
      {
        viewport: 1440,
        label: "desktop chat tri-panel",
        rawIssues: "all evidence uses the same card rhythm",
        rumiIssues: "messages, tools, and evidence keep distinct roles",
        rawScore: 0.44,
        rumiScore: 0.14,
      },
    ],
    selectedViewport: 390,
    expectedDelta: 0.48,
    expectedRawFailed: 2,
    expectedSelectedProof: "mobile chat stress route",
  },
  {
    name: "analytics dashboard with loading, empty, and anomaly states",
    leaf: {
      id: "analytics-state-stack",
      label: "AnalyticsStateStack",
      purpose: "kpi, chart, anomaly, table, empty state",
      status: "accepted",
      rawCompression: 0.63,
      rumiCompression: 0.18,
      rawActions: 10,
      rumiActions: 3,
      candidates: 3,
      acceptedCandidate: "B",
    },
    gates: [
      { id: "metric-hierarchy", label: "Metric hierarchy", raw: "fail", rumi: "pass", detail: "raw cards make headline values and loading skeletons equal weight" },
      { id: "empty-state", label: "Filtered empty state", raw: "warn", rumi: "pass", detail: "rumi gives filtered empty state its own recovery action" },
      { id: "table-scroll", label: "Drilldown table scroll", raw: "fail", rumi: "pass", detail: "raw mobile table drops owner and anomaly cause columns" },
    ],
    proofs: [
      {
        viewport: 390,
        label: "mobile metric route",
        rawIssues: "chart axis, spinner, and no-data copy overlap",
        rumiIssues: "metric, chart, empty state, and table are separate routes",
        rawScore: 0.68,
        rumiScore: 0.22,
      },
      {
        viewport: 768,
        label: "tablet anomaly split",
        rawIssues: "loading and anomaly cards compete in the same row",
        rumiIssues: "anomaly list keeps priority while chart loads",
        rawScore: 0.5,
        rumiScore: 0.19,
      },
      {
        viewport: 1440,
        label: "desktop analytics console",
        rawIssues: "dense table, filters, and chart share one visual priority",
        rumiIssues: "filters affect only the drilldown surface",
        rawScore: 0.39,
        rumiScore: 0.13,
      },
    ],
    selectedViewport: 768,
    expectedDelta: 0.45,
    expectedRawFailed: 2,
    expectedSelectedProof: "tablet anomaly split",
  },
  {
    name: "kanban project management board under mobile compression",
    leaf: {
      id: "kanban-mobile-compression",
      label: "KanbanMobileCompression",
      purpose: "lane route, task card, detail drawer, blocked state",
      status: "review",
      rawCompression: 0.71,
      rumiCompression: 0.26,
      rawActions: 8,
      rumiActions: 3,
      candidates: 2,
      acceptedCandidate: "pending",
    },
    gates: [
      { id: "lane-overflow", label: "Lane overflow", raw: "fail", rumi: "pass", detail: "raw keeps four board columns on phone width" },
      { id: "blocked-detail", label: "Blocked detail", raw: "warn", rumi: "pass", detail: "rumi carries blocked reason as text, not color alone" },
      { id: "drag-target", label: "Drag target clarity", raw: "fail", rumi: "pass", detail: "raw touch targets are ambiguous between lanes" },
    ],
    proofs: [
      {
        viewport: 390,
        label: "mobile swimlane stress",
        rawIssues: "four columns squeeze task cards until owner and due date vanish",
        rumiIssues: "one lane per route with explicit move controls",
        rawScore: 0.74,
        rumiScore: 0.27,
      },
      {
        viewport: 768,
        label: "tablet two-lane planning",
        rawIssues: "detail drawer crowds review column",
        rumiIssues: "drawer becomes route-adjacent and preserves lane width",
        rawScore: 0.53,
        rumiScore: 0.23,
      },
      {
        viewport: 1440,
        label: "desktop board with detail drawer",
        rawIssues: "card metadata repeats across every lane",
        rumiIssues: "cards stay lean while drawer owns history",
        rawScore: 0.42,
        rumiScore: 0.17,
      },
    ],
    selectedViewport: 390,
    expectedDelta: 0.45,
    expectedRawFailed: 2,
    expectedSelectedProof: "mobile swimlane stress",
  },
  {
    name: "ecommerce product configurator with variant and stock errors",
    leaf: {
      id: "product-configurator",
      label: "ProductConfigurator",
      purpose: "gallery, swatches, price, inventory, add-to-cart",
      status: "accepted",
      rawCompression: 0.68,
      rumiCompression: 0.23,
      rawActions: 13,
      rumiActions: 4,
      candidates: 3,
      acceptedCandidate: "A",
    },
    gates: [
      { id: "variant-state", label: "Variant state", raw: "fail", rumi: "pass", detail: "raw buries unavailable and selected swatches in the same tone" },
      { id: "price-proof", label: "Price proof", raw: "warn", rumi: "pass", detail: "rumi separates price, promo, tax, and shipping promises" },
      { id: "cart-error", label: "Add-to-cart error", raw: "fail", rumi: "pass", detail: "rumi gives stock error and recovery action a dedicated leaf" },
    ],
    proofs: [
      {
        viewport: 390,
        label: "mobile configurator stack",
        rawIssues: "gallery, variant matrix, and cart CTA fight for first screen",
        rumiIssues: "gallery, variant picker, and cart CTA become ordered surfaces",
        rawScore: 0.7,
        rumiScore: 0.25,
      },
      {
        viewport: 768,
        label: "tablet product split",
        rawIssues: "stock error pushes price below the fold",
        rumiIssues: "price and selected variant stay pinned",
        rawScore: 0.52,
        rumiScore: 0.21,
      },
      {
        viewport: 1440,
        label: "desktop configurator comparison",
        rawIssues: "review, promo, and stock cards repeat the same hierarchy",
        rumiIssues: "purchase path and supporting proof remain distinct",
        rawScore: 0.41,
        rumiScore: 0.16,
      },
    ],
    selectedViewport: 1440,
    expectedDelta: 0.45,
    expectedRawFailed: 2,
    expectedSelectedProof: "desktop configurator comparison",
  },
  {
    name: "medical intake form with validation and consent recovery",
    leaf: {
      id: "clinical-intake-form",
      label: "ClinicalIntakeForm",
      purpose: "patient details, validation, consent, recovery",
      status: "accepted",
      rawCompression: 0.65,
      rumiCompression: 0.2,
      rawActions: 12,
      rumiActions: 4,
      candidates: 3,
      acceptedCandidate: "B",
    },
    gates: [
      { id: "field-errors", label: "Field errors remain attached", raw: "fail", rumi: "pass", detail: "raw summary separates errors from their form groups" },
      { id: "consent-copy", label: "Consent copy survives", raw: "fail", rumi: "pass", detail: "rumi keeps consent, privacy, and submit states separate" },
      { id: "empty-docs", label: "Empty document state", raw: "warn", rumi: "pass", detail: "rumi explains missing attachments without blocking the form" },
    ],
    proofs: [
      {
        viewport: 390,
        label: "mobile clinical form route",
        rawIssues: "inline errors and consent copy stack into an unreadable block",
        rumiIssues: "form sections, errors, consent, and submit recovery split cleanly",
        rawScore: 0.67,
        rumiScore: 0.22,
      },
      {
        viewport: 768,
        label: "tablet consent drawer",
        rawIssues: "consent drawer hides the invalid field",
        rumiIssues: "drawer mirrors active invalid field and recovery action",
        rawScore: 0.48,
        rumiScore: 0.19,
      },
      {
        viewport: 1440,
        label: "desktop clinical review",
        rawIssues: "review, validation, and submission compete in one panel",
        rumiIssues: "review panel owns summary while form keeps edit controls",
        rawScore: 0.38,
        rumiScore: 0.14,
      },
    ],
    selectedViewport: 768,
    expectedDelta: 0.45,
    expectedRawFailed: 2,
    expectedSelectedProof: "tablet consent drawer",
  },
  {
    name: "fintech transfer form with risk review and long errors",
    leaf: {
      id: "fintech-transfer-form",
      label: "FintechTransferForm",
      purpose: "recipient, amount, risk review, confirmation",
      status: "accepted",
      rawCompression: 0.66,
      rumiCompression: 0.19,
      rawActions: 11,
      rumiActions: 3,
      candidates: 3,
      acceptedCandidate: "C",
    },
    gates: [
      { id: "risk-copy", label: "Risk review copy", raw: "fail", rumi: "pass", detail: "raw hides long risk explanation under the confirmation CTA" },
      { id: "amount-validation", label: "Amount validation", raw: "fail", rumi: "pass", detail: "rumi keeps amount error, limits, and fee preview in separate slots" },
      { id: "receipt-empty", label: "Receipt empty state", raw: "warn", rumi: "pass", detail: "rumi gives pending receipt a calm post-submit state" },
    ],
    proofs: [
      {
        viewport: 390,
        label: "mobile risk review",
        rawIssues: "long compliance copy pushes confirm button off screen",
        rumiIssues: "risk review is a step with pinned confirmation action",
        rawScore: 0.69,
        rumiScore: 0.21,
      },
      {
        viewport: 768,
        label: "tablet transfer review",
        rawIssues: "fee preview and limit error collapse into the same message",
        rumiIssues: "fee, limit, and recipient proof stay separately scannable",
        rawScore: 0.51,
        rumiScore: 0.2,
      },
      {
        viewport: 1440,
        label: "desktop transfer ledger",
        rawIssues: "ledger, transfer form, and receipt share identical cards",
        rumiIssues: "ledger is supporting proof while transfer remains primary",
        rawScore: 0.4,
        rumiScore: 0.15,
      },
    ],
    selectedViewport: 390,
    expectedDelta: 0.47,
    expectedRawFailed: 2,
    expectedSelectedProof: "mobile risk review",
  },
  {
    name: "dense Japanese enterprise approval UI with nested tables",
    leaf: {
      id: "jp-enterprise-approval-grid",
      label: "JapaneseEnterpriseApprovalGrid",
      purpose: "nested table, approval chain, long labels, filters",
      status: "review",
      rawCompression: 0.74,
      rumiCompression: 0.28,
      rawActions: 16,
      rumiActions: 4,
      candidates: 2,
      acceptedCandidate: "pending",
    },
    gates: [
      { id: "long-labels", label: "Long Japanese labels", raw: "fail", rumi: "pass", detail: "raw table repeats truncated department and approval labels" },
      { id: "nested-surface", label: "Nested surface compression", raw: "fail", rumi: "pass", detail: "rumi separates approval chain, row detail, and filters" },
      { id: "bulk-actions", label: "Bulk action budget", raw: "fail", rumi: "pass", detail: "raw exposes every batch action at phone width" },
      { id: "empty-filter", label: "Filtered empty state", raw: "warn", rumi: "pass", detail: "rumi keeps filter recovery visible" },
    ],
    proofs: [
      {
        viewport: 390,
        label: "mobile approval queue",
        rawIssues: "dense table becomes horizontal scroll with hidden approvals",
        rumiIssues: "queue route, row detail, and approval actions are separated",
        rawScore: 0.78,
        rumiScore: 0.3,
      },
      {
        viewport: 768,
        label: "tablet approval split",
        rawIssues: "filters, table, and detail panel produce nested cards",
        rumiIssues: "filters control queue while row detail owns nested fields",
        rawScore: 0.57,
        rumiScore: 0.25,
      },
      {
        viewport: 1440,
        label: "desktop enterprise approval",
        rawIssues: "approval chain and audit log are visually compressed",
        rumiIssues: "approval chain, audit log, and row actions are distinct",
        rawScore: 0.46,
        rumiScore: 0.18,
      },
    ],
    selectedViewport: 390,
    expectedDelta: 0.46,
    expectedRawFailed: 3,
    expectedSelectedProof: "mobile approval queue",
  },
];

function renderComparator(): string {
  return renderToStaticMarkup(createElement(UiPrecisionComparator));
}

test("compressionDelta reports the raw to recursive split improvement", () => {
  assert.equal(
    compressionDelta({
      id: "reply-composer",
      label: "ReplyComposer",
      purpose: "draft, recover, send",
      status: "accepted",
      rawCompression: 0.57,
      rumiCompression: 0.24,
      rawActions: 11,
      rumiActions: 3,
      candidates: 2,
      acceptedCandidate: "A",
    }),
    0.33,
  );
});

test("proofForViewport falls back to the mobile proof for unknown values", () => {
  assert.equal(proofForViewport(390).label, "mobile chat route");
  assert.equal(proofForViewport(999 as 390).viewport, 390);
});

test("gateSummary counts raw failures without penalizing the accepted Rumi path", () => {
  assert.deepEqual(
    gateSummary([
      { id: "a", label: "A", raw: "fail", rumi: "pass", detail: "" },
      { id: "b", label: "B", raw: "warn", rumi: "pass", detail: "" },
      { id: "c", label: "C", raw: "fail", rumi: "pass", detail: "" },
    ]),
    { rawFailed: 2, rumiFailed: 0 },
  );
});

test("promptFingerprint is stable for the shared fairness prompt", () => {
  assert.equal(promptFingerprint("same prompt"), promptFingerprint("same prompt"));
  assert.notEqual(promptFingerprint("same prompt"), promptFingerprint("different prompt"));
});

test("advanced website and app fixtures preserve recursive split score advantages", () => {
  for (const scenario of advancedComparatorCases) {
    assert.equal(compressionDelta(scenario.leaf), scenario.expectedDelta, scenario.name);
    assert.ok(scenario.leaf.rawCompression > scenario.leaf.rumiCompression, `${scenario.name} compression`);
    assert.ok(scenario.leaf.rawActions > scenario.leaf.rumiActions, `${scenario.name} action budget`);

    assert.deepEqual(
      gateSummary(scenario.gates),
      { rawFailed: scenario.expectedRawFailed, rumiFailed: 0 },
      scenario.name,
    );

    const selectedProof = proofForViewport(scenario.selectedViewport, scenario.proofs);
    assert.equal(selectedProof.label, scenario.expectedSelectedProof, scenario.name);
    assert.ok(selectedProof.rawScore > selectedProof.rumiScore, `${scenario.name} viewport comparison`);

    const fallbackProof = proofForViewport(999 as PrecisionViewport, scenario.proofs);
    assert.equal(fallbackProof.label, scenario.proofs[0].label, scenario.name);
  }
});

test("advanced fixtures cover diverse frontend comparator stress domains", () => {
  const names = advancedComparatorCases.map((scenario) => scenario.name).join(" / ");

  assert.match(names, /AI chat app/);
  assert.match(names, /analytics dashboard/);
  assert.match(names, /kanban project management/);
  assert.match(names, /ecommerce product configurator/);
  assert.match(names, /medical intake form/);
  assert.match(names, /fintech transfer form/);
  assert.match(names, /dense Japanese enterprise approval UI/);
});

test("scenario library exposes eight diverse website and app presets", () => {
  assert.deepEqual(
    uiPrecisionScenarioLibrary.map((scenario) => scenario.label),
    [
      "AI Chat App",
      "Support Inbox",
      "Analytics Console",
      "Kanban Planner",
      "Ecommerce Configurator",
      "Clinical Intake",
      "Fintech Approval",
      "Data Grid Admin",
    ],
  );
});

test("scenario library keeps real UI presets backed by recursive evidence", () => {
  for (const scenario of uiPrecisionScenarioLibrary) {
    assert.ok(scenario.request.length > 80, `${scenario.id} should keep a substantive shared request brief`);
    assert.ok(scenario.leaves.length >= 4, `${scenario.id} should split into multiple leaf contracts`);
    assert.equal(scenario.viewportProofs.length, 3, `${scenario.id} should cover mobile, tablet, and desktop`);
    assert.ok(scenario.gates.some((gate) => gate.raw === "fail"), `${scenario.id} should show raw hard gate failures`);
    assert.equal(gateSummary(scenario.gates).rumiFailed, 0, `${scenario.id} should keep Rumi accepted path passing`);
    assert.ok(
      scenario.leaves.some((leaf) => leaf.candidates >= 2 && leaf.acceptedCandidate !== "pending"),
      `${scenario.id} should include multi-candidate selection evidence`,
    );
  }
});

test("scenario library improves compression, actions, and viewport scores for every preset", () => {
  for (const scenario of uiPrecisionScenarioLibrary) {
    const rawCompression =
      scenario.leaves.reduce((total, leaf) => total + leaf.rawCompression, 0) / scenario.leaves.length;
    const rumiCompression =
      scenario.leaves.reduce((total, leaf) => total + leaf.rumiCompression, 0) / scenario.leaves.length;
    const rawActions = scenario.leaves.reduce((total, leaf) => total + leaf.rawActions, 0);
    const rumiActions = scenario.leaves.reduce((total, leaf) => total + leaf.rumiActions, 0);

    assert.ok(rumiCompression < rawCompression, `${scenario.id} should lower compression`);
    assert.ok(rumiActions < rawActions, `${scenario.id} should lower visible actions`);
    for (const proof of scenario.viewportProofs) {
      assert.ok(proof.rumiScore < proof.rawScore, `${scenario.id}/${proof.viewport} should improve viewport proof`);
      assert.match(proof.rawIssues, /\S/);
      assert.match(proof.rumiIssues, /\S/);
    }
  }
});

test("UiPrecisionComparator renders the MiMo and recursive split comparison labels", () => {
  const html = renderComparator();

  assert.match(html, /Rumi UI Design Scenario Demo/);
  assert.match(html, /AI Chat App/);
  assert.match(html, /Ecommerce Configurator/);
  assert.match(html, /Clinical Intake/);
  assert.match(html, /Fintech Approval/);
  assert.match(html, /Data Grid Admin/);
  assert.match(html, /MiMo V2\.5 Pro raw/);
  assert.match(html, /Rumi recursive split/);
  assert.match(html, /Static scenario disclosure/);
  assert.match(html, /Human hints/);
  assert.match(html, /input: shared request brief only/);
});

test("UiPrecisionComparator exposes the advanced scenario selector contract", () => {
  const html = renderComparator();

  assert.match(html, /aria-label="App scenarios"/);
  assert.match(html, /AI Chat App/);
  assert.match(html, /RAG chat with tools/);
  assert.match(html, /Support Inbox/);
  assert.match(html, /Japanese support workflow/);
  assert.match(html, /Analytics Console/);
  assert.match(html, /Metric drill-down console/);
  assert.match(html, /Kanban Planner/);
  assert.match(html, /Team planning board/);
  assert.match(html, /Ecommerce Configurator/);
  assert.match(html, /B2B product configuration/);
  assert.match(html, /Clinical Intake/);
  assert.match(html, /Healthcare form and triage/);
  assert.match(html, /Fintech Approval/);
  assert.match(html, /Risk decision workflow/);
  assert.match(html, /Data Grid Admin/);
  assert.match(html, /Dense enterprise table/);
  assert.match(html, /Request brief/);
  assert.match(html, /Recursive split tree/);
});

test("UiPrecisionComparator marks raw and recursive previews with comparison metadata", () => {
  const html = renderComparator();

  assert.match(html, /data-rumi-node="mimo-raw-preview"/);
  assert.match(html, /data-rumi-node="rumi-recursive-preview"/);
  assert.match(html, /data-rumi-density="over-compressed"/);
  assert.match(html, /data-rumi-density="recursive-detail"/);
  assert.match(html, /data-rumi-role="comparison-render"/);
  assert.match(html, /split 5 leaves/);
  assert.match(html, /3 hard fails/);
  assert.match(html, /0 hard fails/);
  assert.match(html, /3-&gt;0 fail/);
});

test("UiPrecisionComparator renders AI chat responsive proof and nested surface risk", () => {
  const html = renderComparator();

  assert.match(html, /mobile chat route/);
  assert.match(html, /tablet source drawer/);
  assert.match(html, /desktop three-panel/);
  assert.match(html, /generic chat skeleton \/ weak source proof/);
  assert.match(html, /all chat leaves accepted/);
  assert.match(html, /68%/);
  assert.match(html, /51%/);
  assert.match(html, /43%/);
});

test("UiPrecisionComparator keeps long AI chat copy, sources, and action budgets visible", () => {
  const html = renderComparator();
  const longJapaneseQuestion = new RegExp("RAG\\u3068\\u306f\\u4f55\\u304b\\u3092\\u8aac\\u660e\\u3057\\u3066", "u");

  assert.match(html, longJapaneseQuestion);
  assert.match(html, /rag-overview\.pdf page 3/);
  assert.match(html, /docs\/rag-overview\.pdf p\.3/);
  assert.match(html, /source trust unclear/);
  assert.match(html, /sources readable/);
  assert.match(html, /10 visible actions/);
  assert.match(html, /3 visible actions/);
  assert.match(html, /hard gates 1 \/ 6/);
  assert.match(html, /hard gates 6 \/ 6/);
});

test("UiPrecisionComparator exposes selected leaf scoring and tournament comparison", () => {
  const html = renderComparator();

  assert.match(html, /MessageStream \/ AI Chat App \/ viewport 1440px/);
  assert.match(html, /12 actions/);
  assert.match(html, /4 actions/);
  assert.match(html, /39%/);
  assert.match(html, /visible actions/);
  assert.match(html, /Candidate A/);
  assert.match(html, /Candidate B/);
  assert.match(html, /Candidate C/);
  assert.match(html, /42%/);
});

test("promptFingerprint differentiates long, loading, error, and empty state briefs", () => {
  const prompts = [
    "AI chat app with long answer, loading tool call, source error, and empty source fallback",
    "Analytics dashboard with loading chart, empty filtered table, anomaly error, and retry CTA",
    "Medical form with long validation copy, consent loading state, empty attachments, and submit error",
    "Fintech transfer form with risk-review loading, long limit error, empty receipt, and retry",
  ];
  const fingerprints = prompts.map((prompt) => promptFingerprint(prompt));

  assert.equal(new Set(fingerprints).size, prompts.length);
  for (const fingerprint of fingerprints) {
    assert.match(fingerprint, /^prompt-[0-9a-f]{8}$/);
  }
});


test("UI precision demo discloses static fixtures instead of claiming a live benchmark", () => {
  const html = renderToStaticMarkup(createElement(UiPrecisionComparator));
  assert.match(html, /Static demonstration data/);
  assert.match(html, /does not invoke MiMo, Rumi, or any other model/);
  assert.match(html, /Reset demo view/);
  assert.doesNotMatch(html, /Run comparison/);
  assert.doesNotMatch(html, /Fairness lock/);
});
