export const DENSITIES = Object.freeze(["comfortable", "compact", "dataDense"]);

export const REQUIRED_COLOR_ROLES = Object.freeze([
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
]);

export const RUMI_DATA_ATTRIBUTES = Object.freeze([
  "data-rumi-node",
  "data-rumi-density",
  "data-rumi-role",
  "data-rumi-source",
]);

export const DEFAULT_RUMI_FRONTEND_CONFIG = Object.freeze({
  generation: Object.freeze({
    mode: "recursive-zero-to-one",
    rootMayWriteUi: false,
    regenerateInsteadOfPatch: true,
    isolateAgents: "worktree",
  }),
  leafBudget: Object.freeze({
    maxComplexity: 28,
    maxVisualRoles: 18,
    maxInteractiveControls: 5,
    maxMutations: 1,
    maxResponsiveTopologies: 2,
    maxSpecialLayoutAlgorithms: 1,
    minVisualRoles: 2,
  }),
  candidates: Object.freeze({
    foundation: 3,
    pageFrame: 2,
    primaryRegion: 2,
    repeatedCoreComponent: 2,
    secondaryRegion: 1,
  }),
  quality: Object.freeze({
    rejectUnverified: true,
    rejectPrimaryTruncation: true,
    rejectHorizontalOverflow: true,
    rejectArbitraryTokens: true,
    maxCompressionScore: 0.35,
  }),
  viewports: Object.freeze([390, 768, 1024, 1440]),
  textScales: Object.freeze([1, 1.25, 2]),
  scenarios: Object.freeze(["default", "long", "empty", "loading", "error"]),
});

export function deepMerge(base, override = {}) {
  if (!isPlainObject(base) || !isPlainObject(override)) {
    return override === undefined ? base : override;
  }

  const merged = { ...base };
  for (const [key, value] of Object.entries(override)) {
    if (Array.isArray(value)) {
      merged[key] = [...value];
    } else if (isPlainObject(value) && isPlainObject(base[key])) {
      merged[key] = deepMerge(base[key], value);
    } else if (value !== undefined) {
      merged[key] = value;
    }
  }
  return merged;
}

export function defineRumiFrontend(config = {}) {
  const merged = deepMerge(DEFAULT_RUMI_FRONTEND_CONFIG, config);
  assertValidRumiFrontendConfig(merged);
  return deepFreeze(merged);
}

export function validateRumiFrontendConfig(config) {
  const errors = [];
  if (!isPlainObject(config)) {
    return ["config must be an object"];
  }

  if (config.generation?.mode !== "recursive-zero-to-one") {
    errors.push("generation.mode must be recursive-zero-to-one");
  }
  if (config.generation?.rootMayWriteUi !== false) {
    errors.push("generation.rootMayWriteUi must be false");
  }
  if (config.generation?.regenerateInsteadOfPatch !== true) {
    errors.push("generation.regenerateInsteadOfPatch must be true");
  }

  const budget = config.leafBudget ?? {};
  for (const key of [
    "maxComplexity",
    "maxVisualRoles",
    "maxInteractiveControls",
    "maxMutations",
    "maxResponsiveTopologies",
    "maxSpecialLayoutAlgorithms",
  ]) {
    if (!isPositiveNumber(budget[key])) {
      errors.push(`leafBudget.${key} must be a positive number`);
    }
  }

  for (const key of ["foundation", "pageFrame", "primaryRegion", "repeatedCoreComponent", "secondaryRegion"]) {
    if (!Number.isInteger(config.candidates?.[key]) || config.candidates[key] < 1) {
      errors.push(`candidates.${key} must be a positive integer`);
    }
  }

  if (!Array.isArray(config.viewports) || config.viewports.some((value) => !isPositiveNumber(value))) {
    errors.push("viewports must be an array of positive numbers");
  }
  if (!Array.isArray(config.textScales) || config.textScales.some((value) => !isPositiveNumber(value))) {
    errors.push("textScales must be an array of positive numbers");
  }
  if (!Array.isArray(config.scenarios) || config.scenarios.some((value) => typeof value !== "string")) {
    errors.push("scenarios must be an array of strings");
  }
  if (!isPositiveNumber(config.quality?.maxCompressionScore)) {
    errors.push("quality.maxCompressionScore must be a positive number");
  }

  return errors;
}

export function assertValidRumiFrontendConfig(config) {
  const errors = validateRumiFrontendConfig(config);
  if (errors.length > 0) {
    throw new TypeError(`Invalid Rumi frontend config: ${errors.join("; ")}`);
  }
}

export function validateUINode(node, path = "node") {
  const errors = [];
  if (!isPlainObject(node)) {
    return [`${path} must be an object`];
  }
  if (!isNonEmptyString(node.id)) {
    errors.push(`${path}.id must be a non-empty string`);
  }
  if (node.purpose !== undefined && !isNonEmptyString(node.purpose)) {
    errors.push(`${path}.purpose must be a non-empty string when present`);
  }
  if (node.density !== undefined && !DENSITIES.includes(node.density)) {
    errors.push(`${path}.density must be one of ${DENSITIES.join(", ")}`);
  }
  if (node.metrics !== undefined) {
    errors.push(...validateComplexityMetrics(node.metrics, `${path}.metrics`));
  }
  if (node.children !== undefined) {
    if (!Array.isArray(node.children)) {
      errors.push(`${path}.children must be an array`);
    } else {
      node.children.forEach((child, index) => {
        errors.push(...validateUINode(child, `${path}.children[${index}]`));
      });
    }
  }
  return errors;
}

export function assertValidUINode(node) {
  const errors = validateUINode(node);
  if (errors.length > 0) {
    throw new TypeError(`Invalid UI node: ${errors.join("; ")}`);
  }
}

export function validateComplexityMetrics(metrics, path = "metrics") {
  const errors = [];
  if (!isPlainObject(metrics)) {
    return [`${path} must be an object`];
  }
  for (const key of [
    "uniqueVisualRoles",
    "interactiveControls",
    "meaningfulStates",
    "asyncMutations",
    "responsiveTopologies",
    "specialLayoutAlgorithms",
  ]) {
    if (metrics[key] !== undefined && (!Number.isFinite(metrics[key]) || metrics[key] < 0)) {
      errors.push(`${path}.${key} must be a non-negative number`);
    }
  }
  return errors;
}

export function validateComponentContract(contract, path = "contract") {
  const errors = [];
  if (!isPlainObject(contract)) {
    return [`${path} must be an object`];
  }
  for (const key of ["id", "purpose", "primaryPerceptualTask", "density"]) {
    if (!isNonEmptyString(contract[key])) {
      errors.push(`${path}.${key} must be a non-empty string`);
    }
  }
  if (!DENSITIES.includes(contract.density)) {
    errors.push(`${path}.density must be one of ${DENSITIES.join(", ")}`);
  }
  const envelope = contract.layoutEnvelope;
  if (!isPlainObject(envelope)) {
    errors.push(`${path}.layoutEnvelope must be an object`);
  } else {
    for (const key of ["minWidth", "preferredWidth", "maxWidth"]) {
      if (!isPositiveNumber(envelope[key])) {
        errors.push(`${path}.layoutEnvelope.${key} must be a positive number`);
      }
    }
    if (isPositiveNumber(envelope.minWidth) && isPositiveNumber(envelope.maxWidth) && envelope.minWidth > envelope.maxWidth) {
      errors.push(`${path}.layoutEnvelope.minWidth cannot exceed maxWidth`);
    }
  }
  for (const key of ["inputs", "events", "requiredStates", "allowedPrimitives"]) {
    if (!Array.isArray(contract[key]) || contract[key].some((value) => !isNonEmptyString(value))) {
      errors.push(`${path}.${key} must be an array of non-empty strings`);
    }
  }
  if (!Number.isInteger(contract.visibleActionBudget) || contract.visibleActionBudget < 0) {
    errors.push(`${path}.visibleActionBudget must be a non-negative integer`);
  }
  return errors;
}

export function assertValidComponentContract(contract) {
  const errors = validateComponentContract(contract);
  if (errors.length > 0) {
    throw new TypeError(`Invalid component contract: ${errors.join("; ")}`);
  }
}

export function validateFoundation(foundation, path = "foundation") {
  const errors = [];
  if (!isPlainObject(foundation)) {
    return [`${path} must be an object`];
  }
  if (!isPlainObject(foundation.direction)) {
    errors.push(`${path}.direction must be an object`);
  }
  if (!isPlainObject(foundation.typography)) {
    errors.push(`${path}.typography must be an object`);
  }
  if (!isPlainObject(foundation.densityProfiles)) {
    errors.push(`${path}.densityProfiles must be an object`);
  } else {
    for (const density of DENSITIES) {
      if (!isPlainObject(foundation.densityProfiles[density])) {
        errors.push(`${path}.densityProfiles.${density} must be an object`);
      }
    }
  }
  if (!isPlainObject(foundation.colorRoles)) {
    errors.push(`${path}.colorRoles must be an object`);
  } else {
    for (const role of REQUIRED_COLOR_ROLES) {
      if (!isNonEmptyString(foundation.colorRoles[role])) {
        errors.push(`${path}.colorRoles.${role} must be a token reference string`);
      }
    }
  }
  if (!Array.isArray(foundation.typeSpecimen?.viewports)) {
    errors.push(`${path}.typeSpecimen.viewports must list specimen viewports`);
  } else {
    for (const required of [390, 768, 1440]) {
      if (!foundation.typeSpecimen.viewports.includes(required)) {
        errors.push(`${path}.typeSpecimen.viewports must include ${required}`);
      }
    }
  }
  return errors;
}

export function validateDesignIntent(intent, contract, path = "designIntent") {
  const errors = [];
  if (!isPlainObject(intent)) {
    return [`${path} must be an object`];
  }
  for (const key of ["firstVisualFocus", "overflowStrategy", "mobileTransformation"]) {
    if (!isNonEmptyString(intent[key])) {
      errors.push(`${path}.${key} must be a non-empty string`);
    }
  }
  for (const key of ["readingOrder", "visibleAtRest", "progressivelyDisclosed"]) {
    if (!Array.isArray(intent[key]) || intent[key].some((value) => !isNonEmptyString(value))) {
      errors.push(`${path}.${key} must be an array of non-empty strings`);
    }
  }
  for (const key of ["typographyRoles", "colorRoles"]) {
    if (!isPlainObject(intent[key])) {
      errors.push(`${path}.${key} must be an object`);
    }
  }
  if (!Array.isArray(intent.spacingRelationships)) {
    errors.push(`${path}.spacingRelationships must be an array`);
  }
  if (contract?.visibleActionBudget !== undefined && intent.visibleAtRest?.length === 0) {
    errors.push(`${path}.visibleAtRest must include the primary visible affordances`);
  }
  return errors;
}

export function createRumiDataAttributes({ nodeId, density, role, source }) {
  const attrs = {
    "data-rumi-node": nodeId,
    "data-rumi-density": density,
    "data-rumi-role": role,
  };
  if (source) {
    attrs["data-rumi-source"] = source;
  }
  return attrs;
}

export function normalizeRumiId(value) {
  if (!isNonEmptyString(value)) {
    throw new TypeError("Rumi id must be a non-empty string");
  }
  return value
    .trim()
    .replace(/([a-z0-9])([A-Z])/g, "$1-$2")
    .replace(/[^a-zA-Z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase();
}

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isPositiveNumber(value) {
  return Number.isFinite(value) && value > 0;
}

function isNonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

function deepFreeze(value) {
  if (!isPlainObject(value) && !Array.isArray(value)) {
    return value;
  }
  for (const child of Object.values(value)) {
    deepFreeze(child);
  }
  return Object.freeze(value);
}
