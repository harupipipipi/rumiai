import test from "node:test";
import assert from "node:assert/strict";
import {
  buildComponentContract,
  calculateComplexity,
  candidateCountForNode,
  collectLeafNodes,
  findLeafBudgetViolations,
  splitUntilLeafBudget,
} from "../src/index.mjs";
import { defineRumiFrontend } from "../../rumi-ui-contracts/src/index.mjs";

test("complexity follows Rumi visual judgment formula", () => {
  assert.equal(calculateComplexity({
    uniqueVisualRoles: 10,
    interactiveControls: 4,
    meaningfulStates: 3,
    asyncMutations: 1,
    responsiveTopologies: 2,
    specialLayoutAlgorithms: 1,
  }), 41.5);
});

test("recursive splitter keeps bounded child leaves and reports none over budget", () => {
  const tree = splitUntilLeafBudget({
    id: "inbox",
    density: "compact",
    metrics: {
      uniqueVisualRoles: 24,
      interactiveControls: 9,
      meaningfulStates: 6,
      asyncMutations: 1,
      responsiveTopologies: 3,
      specialLayoutAlgorithms: 0,
    },
    children: [
      {
        id: "conversation-list",
        purpose: "Pick the next conversation",
        metrics: {
          uniqueVisualRoles: 10,
          interactiveControls: 2,
          meaningfulStates: 3,
          asyncMutations: 0,
          responsiveTopologies: 1,
          specialLayoutAlgorithms: 0
        }
      },
      {
        id: "reply-composer",
        purpose: "Reply safely",
        primary: true,
        metrics: {
          uniqueVisualRoles: 8,
          interactiveControls: 3,
          meaningfulStates: 3,
          asyncMutations: 1,
          responsiveTopologies: 1,
          specialLayoutAlgorithms: 0
        }
      }
    ]
  });

  assert.deepEqual(collectLeafNodes(tree).map((leaf) => leaf.id), ["conversation-list", "reply-composer"]);
  assert.deepEqual(findLeafBudgetViolations(tree), []);
});

test("candidate counts follow node importance", () => {
  const config = defineRumiFrontend();
  assert.equal(candidateCountForNode({ id: "inbox-page-frame" }, config), 2);
  assert.equal(candidateCountForNode({ id: "reply-composer", primary: true }, config), 2);
  assert.equal(candidateCountForNode({ id: "conversation-item", repeated: true }, config), 2);
  assert.equal(candidateCountForNode({ id: "customer-context" }, config), 1);
});

test("component contract builder keeps layout envelope and state defaults explicit", () => {
  const contract = buildComponentContract({
    id: "reply-composer",
    purpose: "Reply safely",
    density: "comfortable",
    requiredStates: ["empty", "editing"],
    metrics: {
      uniqueVisualRoles: 5,
      interactiveControls: 2,
      meaningfulStates: 2,
      asyncMutations: 0,
      responsiveTopologies: 1,
      specialLayoutAlgorithms: 0,
    },
  });

  assert.equal(contract.layoutEnvelope.minWidth, 280);
  assert.equal(contract.visibleActionBudget, 2);
  assert.deepEqual(contract.requiredStates, ["empty", "editing"]);
});
