import test from "node:test";
import assert from "node:assert/strict";
import {
  decideRecovery,
  isPassingCandidate,
  selectPassingCandidate,
  summarizeFailures,
} from "../src/index.mjs";
import { defineRumiFrontend } from "../../rumi-ui-contracts/src/index.mjs";

test("selector chooses lowest-compression passing candidate", () => {
  const config = defineRumiFrontend();
  const selected = selectPassingCandidate([
    { candidateId: "a", compressionScore: 0.3, hardViolations: [], stateCoverage: 1 },
    { candidateId: "b", compressionScore: 0.12, hardViolations: [], stateCoverage: 0.8 },
    { candidateId: "c", compressionScore: 0.01, hardViolations: [{ id: "overflow" }] },
  ], config);

  assert.equal(selected.candidateId, "b");
  assert.equal(isPassingCandidate(selected, config), true);
});

test("recovery regenerates from blank before splitting", () => {
  const decision = decideRecovery({ id: "reply-composer", attempts: 1 }, [
    { candidateId: "a", compressionScore: 0.8, hardViolations: [] },
  ]);

  assert.equal(decision.action, "regenerate");
  assert.equal(decision.includeFailedSource, false);
});

test("recovery splits after repeated blank failures", () => {
  const decision = decideRecovery({ id: "reply-composer", attempts: 2 }, [
    { candidateId: "a", compressionScore: 0.8, hardViolations: [{ id: "action-budget" }] },
  ]);

  assert.equal(decision.action, "split");
  assert.equal(decision.evidence.hardViolations[0].id, "action-budget");
});

test("failure summaries omit failed source code", () => {
  const summary = summarizeFailures([
    {
      candidateId: "a",
      compressionScore: 0.6,
      source: "do not include",
      hardViolations: [{ id: "primary-content-clipped", message: "clipped" }],
    },
  ]);

  assert.deepEqual(Object.keys(summary), ["candidateCount", "hardViolations", "compressionScores"]);
});
