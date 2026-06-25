import { defineRumiFrontend } from "../../rumi-ui-contracts/src/index.mjs";

export function isPassingCandidate(result, config = defineRumiFrontend()) {
  if (!result) {
    return false;
  }
  const hardViolations = result.hardViolations ?? [];
  return hardViolations.length === 0 && result.compressionScore <= config.quality.maxCompressionScore;
}

export function selectPassingCandidate(results, config = defineRumiFrontend()) {
  const passing = results.filter((result) => isPassingCandidate(result, config));
  if (passing.length === 0) {
    return null;
  }

  return [...passing].sort((a, b) => {
    const scoreDelta = a.compressionScore - b.compressionScore;
    if (scoreDelta !== 0) return scoreDelta;
    const stateDelta = numberOrZero(b.stateCoverage) - numberOrZero(a.stateCoverage);
    if (stateDelta !== 0) return stateDelta;
    const screenshotDelta = numberOrZero(b.screenshotCoverage) - numberOrZero(a.screenshotCoverage);
    if (screenshotDelta !== 0) return screenshotDelta;
    return String(a.candidateId ?? "").localeCompare(String(b.candidateId ?? ""));
  })[0];
}

export function summarizeFailures(results) {
  return {
    candidateCount: results.length,
    hardViolations: results.flatMap((result) =>
      (result.hardViolations ?? []).map((violation) => ({
        candidateId: result.candidateId,
        id: violation.id,
        message: violation.message,
      })),
    ),
    compressionScores: results.map((result) => ({
      candidateId: result.candidateId,
      compressionScore: result.compressionScore,
      scores: result.scores,
    })),
  };
}

export function decideRecovery(node, results, config = defineRumiFrontend()) {
  const accepted = selectPassingCandidate(results, config);
  if (accepted) {
    return { action: "accept", candidate: accepted };
  }
  if (numberOrZero(node.attempts) >= 2) {
    return {
      action: "split",
      reason: "all candidates failed after two attempts",
      evidence: summarizeFailures(results),
    };
  }
  return {
    action: "regenerate",
    reason: "all candidates failed hard gate or compression threshold",
    evidence: summarizeFailures(results),
    includeFailedSource: false,
  };
}

export function createTournamentPlan(nodes, candidateCountForNode) {
  return nodes.map((node) => ({
    nodeId: node.id,
    attempts: node.attempts ?? 0,
    candidateCount: candidateCountForNode(node),
    regenerateInsteadOfPatch: true,
  }));
}

function numberOrZero(value) {
  return Number.isFinite(value) ? value : 0;
}
