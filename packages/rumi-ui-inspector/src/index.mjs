import { defineRumiFrontend } from "../../rumi-ui-contracts/src/index.mjs";

export const COMPRESSION_WEIGHTS = Object.freeze({
  gapPressure: 0.25,
  textPressure: 0.2,
  actionPressure: 0.15,
  boundaryPressure: 0.15,
  surfacePressure: 0.1,
  hierarchyFlattening: 0.15,
});

export function inspectCandidate(evidence = {}, contract = {}, config = defineRumiFrontend()) {
  const scores = calculateCompressionPressures(evidence, contract);
  const compressionScore = calculateCompressionScore(scores);
  const hardViolations = hardGateViolations(evidence, contract, config);
  return {
    nodeId: contract.id ?? evidence.nodeId,
    candidateId: evidence.candidateId,
    scores,
    compressionScore,
    hardViolations,
    passed: hardViolations.length === 0 && compressionScore <= config.quality.maxCompressionScore,
  };
}

export function calculateCompressionPressures(evidence = {}, contract = {}) {
  return {
    gapPressure: gapPressure(evidence.gaps),
    textPressure: textPressure(evidence.text),
    actionPressure: actionPressure(evidence.actions, contract),
    boundaryPressure: boundaryPressure(evidence.regions),
    surfacePressure: surfacePressure(evidence.surfaces),
    hierarchyFlattening: hierarchyFlattening(evidence.hierarchy),
    responsiveStress: responsiveStress(evidence.responsive),
  };
}

export function calculateCompressionScore(scores) {
  const weighted =
    scores.gapPressure * COMPRESSION_WEIGHTS.gapPressure
    + scores.textPressure * COMPRESSION_WEIGHTS.textPressure
    + scores.actionPressure * COMPRESSION_WEIGHTS.actionPressure
    + scores.boundaryPressure * COMPRESSION_WEIGHTS.boundaryPressure
    + scores.surfacePressure * COMPRESSION_WEIGHTS.surfacePressure
    + scores.hierarchyFlattening * COMPRESSION_WEIGHTS.hierarchyFlattening;
  return round3(weighted);
}

export function hardGateViolations(evidence = {}, contract = {}, config = defineRumiFrontend()) {
  const violations = [];
  const actionCount = visibleActionCount(evidence.actions);

  if (config.quality.rejectPrimaryTruncation && evidence.primaryContentClipped === true) {
    violations.push(makeViolation("primary-content-clipped", "primary content is clipped"));
  }
  if (evidence.primaryActionVisible === false) {
    violations.push(makeViolation("primary-action-hidden", "primary action is not visible"));
  }
  if (config.quality.rejectHorizontalOverflow && evidence.horizontalOverflow === true) {
    violations.push(makeViolation("horizontal-overflow", "unexpected horizontal overflow detected"));
  }
  if (evidence.unreadableControlLabel === true) {
    violations.push(makeViolation("control-label-unreadable", "major control label is unreadable"));
  }
  if (Number.isInteger(contract.visibleActionBudget) && actionCount > contract.visibleActionBudget) {
    violations.push(makeViolation(
      "visible-action-budget-exceeded",
      `visible actions ${actionCount} exceed budget ${contract.visibleActionBudget}`,
    ));
  }
  for (const region of evidence.regions ?? []) {
    if (Number.isFinite(region.actualPadding) && Number.isFinite(region.requiredPadding) && region.actualPadding < region.requiredPadding) {
      violations.push(makeViolation(
        "region-padding-violation",
        `${region.id ?? "region"} padding ${region.actualPadding} is below required ${region.requiredPadding}`,
      ));
    }
  }
  if (contract.density && evidence.density && contract.density !== evidence.density) {
    violations.push(makeViolation("density-mismatch", `contract density ${contract.density} does not match rendered ${evidence.density}`));
  }

  return violations;
}

export function inspectColorUsage(evidence = {}, foundation = {}) {
  const allowedTokens = new Set(Object.values(foundation.colorRoles ?? {}));
  const violations = [];
  const styles = evidence.styles ?? [];

  for (const style of styles) {
    const value = style.value ?? "";
    if (/#[0-9a-fA-F]{3,8}\b/.test(value)) {
      violations.push(makeViolation("arbitrary-hex-color", `${style.source ?? "style"} uses ${value}`));
    }
    if (value.startsWith("var(--") && allowedTokens.size > 0 && !allowedTokens.has(style.token) && style.semanticRole) {
      violations.push(makeViolation("unknown-color-token", `${style.source ?? "style"} uses unapproved token ${style.token}`));
    }
    if (style.semanticRole?.startsWith("status") && style.intent !== "status") {
      violations.push(makeViolation("status-color-misuse", `${style.source ?? "style"} uses status color outside status UI`));
    }
    if (style.stateEncodedByColorOnly === true) {
      violations.push(makeViolation("color-only-state", `${style.source ?? "style"} expresses state by color only`));
    }
  }

  if (Number.isFinite(evidence.accentColorCoverage) && evidence.accentColorCoverage > 0.18) {
    violations.push(makeViolation("accent-color-overuse", `accent coverage ${evidence.accentColorCoverage} exceeds 0.18`));
  }

  return violations;
}

export function gapPressure(gaps = []) {
  return averageSeverity(gaps, (gap) => {
    if (!Number.isFinite(gap.actual) || !Number.isFinite(gap.expected) || gap.expected <= 0) {
      return 0;
    }
    const floor = gap.expected * 0.75;
    return gap.actual < floor ? (floor - gap.actual) / floor : 0;
  });
}

export function boundaryPressure(regions = []) {
  return averageSeverity(regions, (region) => {
    if (!Number.isFinite(region.actualPadding) || !Number.isFinite(region.requiredPadding) || region.requiredPadding <= 0) {
      return 0;
    }
    return region.actualPadding < region.requiredPadding
      ? (region.requiredPadding - region.actualPadding) / region.requiredPadding
      : 0;
  });
}

export function textPressure(text = {}) {
  const samples = Array.isArray(text) ? text : text.samples ?? [];
  const severities = samples.map((sample) => {
    let severity = 0;
    if (sample.clipped) severity += 1;
    if (sample.primaryControlLabelWrapped) severity += 0.8;
    if (sample.excessiveEllipsis) severity += 0.7;
    if (Number.isFinite(sample.lineHeightRatio) && sample.lineHeightRatio < 1.2) severity += 0.5;
    if (sample.layoutBrokenByLongText) severity += 1;
    return clamp01(severity);
  });
  return average(severities);
}

export function actionPressure(actions = {}, contract = {}) {
  const visible = visibleActionCount(actions);
  const budget = Number.isInteger(contract.visibleActionBudget) ? contract.visibleActionBudget : visible;
  if (budget <= 0) {
    return visible > 0 ? 1 : 0;
  }
  return visible > budget ? clamp01((visible - budget) / Math.max(1, budget)) : 0;
}

export function surfacePressure(surfaces = {}) {
  const nestedCards = numberOrZero(surfaces.nestedCards);
  const repeatedBorders = numberOrZero(surfaces.repeatedBorders);
  const enclosingRegions = numberOrZero(surfaces.enclosingRegions);
  const dividers = numberOrZero(surfaces.dividers);
  return clamp01((nestedCards * 0.35 + repeatedBorders * 0.2 + enclosingRegions * 0.25 + dividers * 0.1) / 2);
}

export function hierarchyFlattening(pairs = []) {
  return averageSeverity(pairs, (pair) => {
    const fontSizeDelta = Math.abs(numberOrZero(pair.primaryFontSize) - numberOrZero(pair.secondaryFontSize));
    const weightDelta = Math.abs(numberOrZero(pair.primaryFontWeight) - numberOrZero(pair.secondaryFontWeight));
    const colorDelta = numberOrZero(pair.colorDelta);
    const spacingDelta = Math.abs(numberOrZero(pair.spacingBeforePrimary) - numberOrZero(pair.spacingBeforeSecondary));
    let severity = 0;
    if (fontSizeDelta < 2) severity += 0.3;
    if (weightDelta < 100) severity += 0.3;
    if (colorDelta < 0.12) severity += 0.2;
    if (spacingDelta < 4) severity += 0.2;
    return clamp01(severity);
  });
}

export function responsiveStress(responsive = {}) {
  let severity = 0;
  if (responsive.desktopControlCount === responsive.mobileControlCount && responsive.desktopControlCount > 4) {
    severity += 0.3;
  }
  if (responsive.toolbarWrapped) severity += 0.25;
  if (responsive.primaryActionOffscreen) severity += 0.35;
  if (responsive.horizontalScroll) severity += 0.5;
  if (responsive.excessiveVerticalStacking) severity += 0.25;
  return clamp01(severity);
}

function visibleActionCount(actions = {}) {
  if (Array.isArray(actions)) {
    return actions.filter((action) => action.visible !== false).length;
  }
  if (Array.isArray(actions.items)) {
    return actions.items.filter((action) => action.visible !== false).length;
  }
  return numberOrZero(actions.visibleCount);
}

function averageSeverity(items = [], fn) {
  if (!Array.isArray(items) || items.length === 0) {
    return 0;
  }
  return average(items.map((item) => clamp01(fn(item))));
}

function average(values) {
  if (!Array.isArray(values) || values.length === 0) {
    return 0;
  }
  return round3(values.reduce((sum, value) => sum + value, 0) / values.length);
}

function makeViolation(id, message) {
  return { id, message };
}

function numberOrZero(value) {
  return Number.isFinite(value) ? value : 0;
}

function clamp01(value) {
  if (!Number.isFinite(value)) return 0;
  return Math.min(1, Math.max(0, value));
}

function round3(value) {
  return Math.round(value * 1000) / 1000;
}
