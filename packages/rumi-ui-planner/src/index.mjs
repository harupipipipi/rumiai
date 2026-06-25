import {
  assertValidUINode,
  defineRumiFrontend,
  normalizeRumiId,
} from "../../rumi-ui-contracts/src/index.mjs";

export function calculateComplexity(input = {}) {
  const metrics = input.metrics ?? input.complexityMetrics ?? input;
  const uniqueVisualRoles = numberOrZero(metrics.uniqueVisualRoles);
  const interactiveControls = numberOrZero(metrics.interactiveControls);
  const meaningfulStates = numberOrZero(metrics.meaningfulStates);
  const asyncMutations = numberOrZero(metrics.asyncMutations);
  const responsiveTopologies = numberOrZero(metrics.responsiveTopologies);
  const specialLayoutAlgorithms = numberOrZero(metrics.specialLayoutAlgorithms);

  return round2(
    uniqueVisualRoles
      + interactiveControls * 2
      + meaningfulStates * 1.5
      + asyncMutations * 5
      + responsiveTopologies * 4
      + specialLayoutAlgorithms * 6,
  );
}

export function estimateNodeMetrics(node) {
  if (node.metrics) {
    return { ...node.metrics };
  }

  const children = Array.isArray(node.children) ? node.children : [];
  return {
    uniqueVisualRoles: Math.max(1, children.length * 2),
    interactiveControls: numberOrZero(node.interactiveControls),
    meaningfulStates: Array.isArray(node.requiredStates) ? node.requiredStates.length : 1,
    asyncMutations: numberOrZero(node.asyncMutations),
    responsiveTopologies: numberOrZero(node.responsiveTopologies) || (children.length > 2 ? 2 : 1),
    specialLayoutAlgorithms: numberOrZero(node.specialLayoutAlgorithms),
  };
}

export function leafBudgetViolations(node, config = defineRumiFrontend()) {
  const budget = config.leafBudget;
  const metrics = estimateNodeMetrics(node);
  const violations = [];
  const complexity = calculateComplexity(metrics);

  if (complexity > budget.maxComplexity) {
    violations.push({ rule: "maxComplexity", actual: complexity, limit: budget.maxComplexity });
  }
  if (metrics.uniqueVisualRoles > budget.maxVisualRoles) {
    violations.push({ rule: "maxVisualRoles", actual: metrics.uniqueVisualRoles, limit: budget.maxVisualRoles });
  }
  if (metrics.interactiveControls > budget.maxInteractiveControls) {
    violations.push({
      rule: "maxInteractiveControls",
      actual: metrics.interactiveControls,
      limit: budget.maxInteractiveControls,
    });
  }
  if (metrics.asyncMutations > budget.maxMutations) {
    violations.push({ rule: "maxMutations", actual: metrics.asyncMutations, limit: budget.maxMutations });
  }
  if (metrics.responsiveTopologies > budget.maxResponsiveTopologies) {
    violations.push({
      rule: "maxResponsiveTopologies",
      actual: metrics.responsiveTopologies,
      limit: budget.maxResponsiveTopologies,
    });
  }
  if (metrics.specialLayoutAlgorithms > budget.maxSpecialLayoutAlgorithms) {
    violations.push({
      rule: "maxSpecialLayoutAlgorithms",
      actual: metrics.specialLayoutAlgorithms,
      limit: budget.maxSpecialLayoutAlgorithms,
    });
  }
  if (isTinyFragment(node, metrics, budget)) {
    violations.push({ rule: "minMeaningfulLeaf", actual: metrics.uniqueVisualRoles, limit: budget.minVisualRoles });
  }

  return violations;
}

export function shouldSplitNode(node, config = defineRumiFrontend()) {
  const violations = leafBudgetViolations(node, config);
  return violations.some((violation) => violation.rule !== "minMeaningfulLeaf");
}

export function splitUntilLeafBudget(node, config = defineRumiFrontend()) {
  assertValidUINode(node);
  const normalized = normalizeNode(node);
  return splitNodeRecursive(normalized, config);
}

export function collectLeafNodes(node) {
  if (!Array.isArray(node.children) || node.children.length === 0) {
    return [node];
  }
  return node.children.flatMap((child) => collectLeafNodes(child));
}

export function findLeafBudgetViolations(node, config = defineRumiFrontend()) {
  return collectLeafNodes(node)
    .map((leaf) => ({ node: leaf, violations: leafBudgetViolations(leaf, config) }))
    .filter((entry) => entry.violations.length > 0);
}

export function candidateCountForNode(node, config = defineRumiFrontend()) {
  const importance = node.importance ?? inferImportance(node);
  return config.candidates[importance] ?? config.candidates.secondaryRegion;
}

export function buildComponentContract(node, overrides = {}) {
  const metrics = estimateNodeMetrics(node);
  return {
    id: node.id,
    purpose: node.purpose ?? `Implement ${node.id}`,
    primaryPerceptualTask: node.primaryPerceptualTask ?? node.purpose ?? `Understand ${node.id}`,
    density: node.density ?? "compact",
    layoutEnvelope: {
      minWidth: node.layoutEnvelope?.minWidth ?? 280,
      preferredWidth: node.layoutEnvelope?.preferredWidth ?? 560,
      maxWidth: node.layoutEnvelope?.maxWidth ?? 760,
      heightBehavior: node.layoutEnvelope?.heightBehavior ?? "content",
      mobileBehavior: node.layoutEnvelope?.mobileBehavior ?? "reflow",
    },
    inputs: node.inputs ?? [],
    events: node.events ?? [],
    requiredStates: node.requiredStates ?? ["default"],
    allowedPrimitives: node.allowedPrimitives ?? [],
    visibleActionBudget: node.visibleActionBudget ?? Math.min(3, Math.max(1, metrics.interactiveControls)),
    ...overrides,
  };
}

export function createPageFrameSlots(slots) {
  return Object.fromEntries(
    Object.entries(slots).map(([slotId, slot]) => [
      normalizeRumiId(slotId),
      {
        id: normalizeRumiId(slotId),
        ...slot,
      },
    ]),
  );
}

function splitNodeRecursive(node, config) {
  const metrics = estimateNodeMetrics(node);
  const children = Array.isArray(node.children) ? node.children : [];

  if (!shouldSplitNode({ ...node, metrics }, config)) {
    return { ...node, metrics, complexity: calculateComplexity(metrics) };
  }

  const nextChildren = children.length > 0 ? children : suggestRecursiveSplit(node);
  if (nextChildren.length === 0) {
    return {
      ...node,
      metrics,
      complexity: calculateComplexity(metrics),
      planningStatus: "needs-decomposition",
      budgetViolations: leafBudgetViolations({ ...node, metrics }, config),
    };
  }

  return {
    ...node,
    metrics,
    complexity: calculateComplexity(metrics),
    children: nextChildren.map((child) => splitNodeRecursive(normalizeNode(child, node), config)),
  };
}

function suggestRecursiveSplit(node) {
  if (Array.isArray(node.subregions) && node.subregions.length > 0) {
    return node.subregions;
  }
  if (Array.isArray(node.roleGroups) && node.roleGroups.length > 0) {
    return node.roleGroups.map((group) => ({
      id: group.id,
      purpose: group.purpose,
      density: node.density,
      importance: group.importance ?? "secondaryRegion",
      metrics: group.metrics,
    }));
  }
  return [];
}

function normalizeNode(node, parent) {
  const normalized = {
    ...node,
    id: normalizeRumiId(node.id),
    density: node.density ?? parent?.density ?? "compact",
  };
  if (Array.isArray(node.children)) {
    normalized.children = node.children.map((child) => normalizeNode(child, normalized));
  }
  return normalized;
}

function inferImportance(node) {
  if (node.id.includes("page-frame") || node.id.endsWith("-frame")) {
    return "pageFrame";
  }
  if (node.primary === true || node.id.includes("composer") || node.id.includes("timeline")) {
    return "primaryRegion";
  }
  if (node.repeated === true || node.id.includes("item") || node.id.includes("row")) {
    return "repeatedCoreComponent";
  }
  return "secondaryRegion";
}

function isTinyFragment(node, metrics, budget) {
  const id = node.id ?? "";
  const tinyName = /(^|[-_])(button|icon|label|text|badge)([-_]|$)/i.test(id);
  return tinyName && metrics.uniqueVisualRoles < budget.minVisualRoles && metrics.interactiveControls <= 1;
}

function numberOrZero(value) {
  return Number.isFinite(value) ? value : 0;
}

function round2(value) {
  return Math.round(value * 100) / 100;
}
