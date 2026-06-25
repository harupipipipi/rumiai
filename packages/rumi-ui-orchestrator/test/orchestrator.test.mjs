import test from "node:test";
import assert from "node:assert/strict";
import {
  AGENT_ROLES,
  createAgentTaskPlan,
  createCandidateRequests,
  createWriteScopeGuard,
  generateNode,
} from "../src/index.mjs";
import { defineRumiFrontend } from "../../rumi-ui-contracts/src/index.mjs";

test("write scopes enforce root, leaf, selector, and composition boundaries", () => {
  const workspaceRoot = process.cwd();
  const root = createWriteScopeGuard({ workspaceRoot, role: AGENT_ROLES.ROOT });
  assert.equal(root.canWrite(".rumi/ui/contracts/reply-composer.contract.json"), true);
  assert.equal(root.canWrite("src/features/inbox/ReplyComposer.tsx"), false);

  const leaf = createWriteScopeGuard({
    workspaceRoot,
    role: AGENT_ROLES.LEAF,
    nodeId: "reply-composer",
    candidateId: "a",
  });
  assert.equal(leaf.canWrite(".rumi/ui/candidates/reply-composer/a/Component.tsx"), true);
  assert.equal(leaf.canWrite(".rumi/ui/candidates/reply-composer/b/Component.tsx"), false);

  const selector = createWriteScopeGuard({ workspaceRoot, role: AGENT_ROLES.SELECTOR });
  assert.equal(selector.canWrite(".rumi/ui/accepted/reply-composer"), false);

  const composition = createWriteScopeGuard({ workspaceRoot, role: AGENT_ROLES.COMPOSITION });
  assert.equal(composition.canWrite("src/routes/inbox.tsx"), true);
  assert.equal(composition.canWrite(".rumi/ui/candidates/reply-composer/a/Component.tsx"), false);
});

test("agent task plan creates foundation tournament and leaf candidates", () => {
  const plan = createAgentTaskPlan({
    id: "inbox",
    metrics: {
      uniqueVisualRoles: 1,
      interactiveControls: 0,
      meaningfulStates: 1,
      asyncMutations: 0,
      responsiveTopologies: 1,
      specialLayoutAlgorithms: 0,
    },
    children: [
      {
        id: "reply-composer",
        primary: true,
        metrics: {
          uniqueVisualRoles: 8,
          interactiveControls: 3,
          meaningfulStates: 4,
          asyncMutations: 1,
          responsiveTopologies: 1,
          specialLayoutAlgorithms: 0,
        },
      },
    ],
  }, defineRumiFrontend());

  assert.equal(plan.foundation.length, 3);
  assert.equal(plan.leaves.length, 2);
});

test("candidate requests never include previous implementation", () => {
  const requests = createCandidateRequests({ id: "reply-composer", primary: true }, defineRumiFrontend());
  assert.equal(requests.length, 2);
  assert.equal(requests[0].blankDirectory, true);
  assert.equal(requests[0].includePreviousImplementation, false);
});

test("generateNode accepts passing candidate and stores bundle", async () => {
  const stored = [];
  const result = await generateNode({ id: "reply-composer", primary: true }, {
    agentRunner: async (request) => ({ candidateId: request.candidateId, nodeId: request.nodeId }),
    renderAndInspect: async (candidate) => ({
      candidateId: candidate.candidateId,
      compressionScore: candidate.candidateId === "a" ? 0.2 : 0.3,
      hardViolations: [],
    }),
    storeAcceptedBundle: async (candidate) => stored.push(candidate.candidateId),
  });

  assert.equal(result.status, "accepted");
  assert.equal(result.candidate.candidateId, "a");
  assert.deepEqual(stored, ["a"]);
});

test("generateNode requests blank regeneration without failed source", async () => {
  const result = await generateNode({ id: "reply-composer", primary: true, attempts: 1 }, {
    agentRunner: async (request) => ({ candidateId: request.candidateId, nodeId: request.nodeId }),
    renderAndInspect: async (candidate) => ({
      candidateId: candidate.candidateId,
      compressionScore: 0.8,
      hardViolations: [{ id: "primary-content-clipped", message: "clipped" }],
    }),
    regenerateFromBlank: async (_node, payload) => ({
      status: "regenerate",
      includeFailedSource: payload.includeFailedSource,
      evidence: payload.evidence,
    }),
  });

  assert.equal(result.status, "regenerate");
  assert.equal(result.includeFailedSource, false);
});
