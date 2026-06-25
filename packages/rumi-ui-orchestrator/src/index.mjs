import fs from "node:fs";
import path from "node:path";
import { defineRumiFrontend } from "../../rumi-ui-contracts/src/index.mjs";
import {
  calculateComplexity,
  candidateCountForNode,
  collectLeafNodes,
  splitUntilLeafBudget,
} from "../../rumi-ui-planner/src/index.mjs";
import {
  decideRecovery,
  selectPassingCandidate,
  summarizeFailures,
} from "../../rumi-ui-selector/src/index.mjs";

export const AGENT_ROLES = Object.freeze({
  ROOT: "root-orchestrator",
  FOUNDATION: "foundation-agent",
  LEAF: "leaf-agent",
  COMPOSITION: "composition-agent",
  SELECTOR: "selector-agent",
});

export function createWriteScopeGuard(options) {
  const workspaceRoot = path.resolve(options.workspaceRoot ?? process.cwd());
  const role = options.role;
  const allowedRoots = defaultAllowedRoots({ ...options, workspaceRoot }).map((entry) => path.resolve(workspaceRoot, entry));
  const deniedRoots = defaultDeniedRoots({ ...options, workspaceRoot }).map((entry) => path.resolve(workspaceRoot, entry));

  return {
    role,
    allowedRoots,
    deniedRoots,
    canWrite(filePath) {
      const target = path.resolve(workspaceRoot, filePath);
      const denied = deniedRoots.some((root) => isWithin(root, target));
      const allowed = allowedRoots.some((root) => isWithin(root, target));
      return allowed && !denied;
    },
    assertCanWrite(filePath) {
      if (!this.canWrite(filePath)) {
        throw new Error(`${role} cannot write ${filePath}`);
      }
    },
  };
}

export function createAgentTaskPlan(uiTree, config = defineRumiFrontend()) {
  const leaves = collectLeafNodes(uiTree);
  return {
    foundation: Array.from({ length: config.candidates.foundation }, (_, index) => ({
      role: AGENT_ROLES.FOUNDATION,
      candidateId: candidateLabel(index),
      outputDir: `.rumi/ui/foundation/${candidateLabel(index)}`,
    })),
    leaves: leaves.flatMap((leaf) =>
      Array.from({ length: candidateCountForNode(leaf, config) }, (_, index) => ({
        role: AGENT_ROLES.LEAF,
        nodeId: leaf.id,
        candidateId: candidateLabel(index),
        outputDir: `.rumi/ui/candidates/${leaf.id}/${candidateLabel(index)}`,
        contractPath: `.rumi/ui/contracts/${leaf.id}.contract.json`,
      })),
    ),
  };
}

export function createArtifactStore(runRoot = ".rumi/ui") {
  const root = path.normalize(runRoot);
  return {
    root,
    paths: {
      constitution: path.join(root, "constitution.json"),
      foundation: path.join(root, "foundation"),
      blueprints: path.join(root, "blueprints"),
      contracts: path.join(root, "contracts"),
      candidates: path.join(root, "candidates"),
      accepted: path.join(root, "accepted"),
      renders: path.join(root, "renders"),
      reports: path.join(root, "reports"),
    },
    ensure() {
      for (const dir of Object.values(this.paths)) {
        if (path.extname(dir)) continue;
        fs.mkdirSync(dir, { recursive: true });
      }
    },
    writeJson(relativePath, value) {
      const target = path.join(root, relativePath);
      fs.mkdirSync(path.dirname(target), { recursive: true });
      fs.writeFileSync(target, `${JSON.stringify(value, null, 2)}\n`, "utf8");
      return target;
    },
  };
}

export async function generateNode(node, context) {
  const config = defineRumiFrontend(context.config ?? {});
  const complexity = calculateComplexity(node);
  if (complexity > config.leafBudget.maxComplexity && Array.isArray(node.children) && node.children.length > 0) {
    const planned = splitUntilLeafBudget(node, config);
    const generatedChildren = [];
    for (const child of planned.children ?? []) {
      generatedChildren.push(await generateNode(child, context));
    }
    return {
      status: "split",
      nodeId: node.id,
      children: generatedChildren,
    };
  }

  const candidateRequests = createCandidateRequests(node, config);
  const candidates = await Promise.all(candidateRequests.map((request) => context.agentRunner(request)));
  const inspected = await Promise.all(candidates.map((candidate) => context.renderAndInspect(candidate, node.contract ?? node)));
  const accepted = (context.selectPassingCandidate ?? selectPassingCandidate)(inspected, config);

  if (accepted) {
    if (context.storeAcceptedBundle) {
      await context.storeAcceptedBundle(accepted);
    }
    return {
      status: "accepted",
      nodeId: node.id,
      candidate: accepted,
    };
  }

  const attempts = node.attempts ?? 0;
  const recovery = decideRecovery({ ...node, attempts }, inspected, config);
  if (recovery.action === "split") {
    const splitNode = context.splitNode ?? splitUntilLeafBudget;
    return {
      status: "split-required",
      nodeId: node.id,
      evidence: summarizeFailures(inspected),
      tree: splitNode(node, config),
    };
  }

  if (!context.regenerateFromBlank) {
    return {
      status: "regenerate-required",
      nodeId: node.id,
      evidence: summarizeFailures(inspected),
      includeFailedSource: false,
    };
  }

  return context.regenerateFromBlank(node, {
    evidence: summarizeFailures(inspected),
    includeFailedSource: false,
  });
}

export function createCandidateRequests(node, config = defineRumiFrontend()) {
  const count = candidateCountForNode(node, config);
  return Array.from({ length: count }, (_, index) => ({
    nodeId: node.id,
    role: AGENT_ROLES.LEAF,
    candidateId: candidateLabel(index),
    outputDir: `.rumi/ui/candidates/${node.id}/${candidateLabel(index)}`,
    contract: node.contract ?? node,
    blankDirectory: true,
    includePreviousImplementation: false,
  }));
}

export function writeJsonScoped(guard, filePath, value) {
  guard.assertCanWrite(filePath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function defaultAllowedRoots(options) {
  const nodeId = options.nodeId;
  const candidateId = options.candidateId;
  switch (options.role) {
    case AGENT_ROLES.ROOT:
      return [".rumi/ui/constitution.json", ".rumi/ui/blueprints", ".rumi/ui/contracts", ".rumi/ui/reports"];
    case AGENT_ROLES.FOUNDATION:
      return [".rumi/ui/foundation", "src/ui/primitives", "src/ui/tokens"];
    case AGENT_ROLES.LEAF:
      if (!nodeId || !candidateId) {
        return [];
      }
      return [path.join(".rumi/ui/candidates", nodeId, candidateId)];
    case AGENT_ROLES.COMPOSITION:
      return ["src/routes", "src/pages", "src/app", "src/features", ".rumi/ui/accepted"];
    case AGENT_ROLES.SELECTOR:
      return [];
    default:
      return [];
  }
}

function defaultDeniedRoots(options) {
  switch (options.role) {
    case AGENT_ROLES.ROOT:
      return ["src", "app", "routes", "pages"];
    case AGENT_ROLES.COMPOSITION:
      return [".rumi/ui/candidates"];
    case AGENT_ROLES.SELECTOR:
      return [".", "src", ".rumi"];
    default:
      return [];
  }
}

function isWithin(root, target) {
  const relative = path.relative(root, target);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

function candidateLabel(index) {
  return String.fromCharCode("a".charCodeAt(0) + index);
}
