import test from "node:test";
import assert from "node:assert/strict";

import {
  applyAgentTemplate,
  buildCreateAgentPayload,
  validateCreateAgentDraft,
  type AgentWizardDraft,
} from "./CreateAgentWizard";

const draft: AgentWizardDraft = {
  template_id: "coding",
  name: " Worker ",
  profile_id: " local_agent ",
  role: " Build UI ",
  model: "openrouter/test",
  api_key_id: "key-1",
  provider_id: "openrouter",
  browser_profile_id: "default",
  browser_enabled: true,
  computer_enabled: false,
  tools: ["coding_file_read"],
  run_mode: "scheduled",
  interval_minutes: 15,
  start_now: true,
  stop_on_failure: true,
  max_cost_usd: 2.5,
  approval_mode: "manual_only",
};

test("create agent wizard builds a trimmed API payload", () => {
  const payload = buildCreateAgentPayload(draft);

  assert.equal(payload.name, "Worker");
  assert.equal(payload.profile_id, "local_agent");
  assert.equal(payload.role, "Build UI");
  assert.equal(payload.schedule?.enabled, true);
  assert.equal(payload.schedule?.interval_minutes, 15);
  assert.deepEqual(payload.tool_policy?.require_approval_for, ["low", "medium", "high"]);
});

test("create agent wizard removes browser profile when browser is disabled", () => {
  const payload = buildCreateAgentPayload({ ...draft, browser_enabled: false });

  assert.equal(payload.browser_enabled, false);
  assert.equal(payload.browser_profile_id, null);
});

test("create agent wizard validates required identity fields", () => {
  assert.deepEqual(validateCreateAgentDraft({ ...draft, name: "", role: "" }), [
    "Agent name is required.",
    "Role is required.",
  ]);
});

test("template application keeps existing fields and replaces declared defaults", () => {
  const next = applyAgentTemplate(draft, {
    id: "ops",
    name: "Ops",
    profile_id: "defaultspack.operations_company",
    role: "Monitor",
    tools: ["browser_use"],
    lifecycle: "non_stop",
  });

  assert.equal(next.name, draft.name);
  assert.equal(next.profile_id, "defaultspack.operations_company");
  assert.deepEqual(next.tools, ["browser_use"]);
  assert.equal(next.run_mode, "non_stop");
});
