from __future__ import annotations

from pathlib import Path
from typing import Any

from domain.ui_compiler import CandidateBundle, CompressionIssue, CompressionReport, RenderMatrix

from .validation import validate_candidate_bundle


class CompressionInspector:
    def inspect_candidate(
        self,
        *,
        bundle: CandidateBundle,
        contract: dict[str, Any],
        render_matrix: RenderMatrix,
    ) -> CompressionReport:
        root = Path(bundle.root)
        validation = validate_candidate_bundle(root, contract)
        issues = [
            CompressionIssue(
                code=str(issue.get("code")),
                severity=str(issue.get("severity") or "major"),
                message=str(issue.get("message") or issue.get("code")),
                evidence=dict(issue.get("evidence") or {}),
            )
            for issue in validation.get("issues", [])
            if isinstance(issue, dict)
        ]
        metrics = _aggregate_metrics(render_matrix)
        issues.extend(_metric_issues(metrics, contract))
        score = _score(metrics, issues)
        status = "fail" if _has_blocker(issues) or score > 0.35 else "pass"
        return CompressionReport(
            node_id=bundle.node_id,
            candidate_id=bundle.candidate_id,
            status=status,
            compression_score=round(score, 3),
            metrics=metrics,
            issues=issues,
        )

    def inspect_page(self, *, render_matrix: RenderMatrix, accepted_count: int) -> dict[str, Any]:
        metrics = _aggregate_metrics(render_matrix)
        issues = _metric_issues(metrics, {"visibleActionBudget": max(3, accepted_count * 2), "requiredStates": []})
        return {
            "status": "fail" if _has_blocker(issues) else "pass",
            "compressionScore": round(_score(metrics, issues), 3),
            "metrics": metrics,
            "issues": [issue.to_dict() for issue in issues],
        }


def _aggregate_metrics(render_matrix: RenderMatrix) -> dict[str, float]:
    snapshots = render_matrix.snapshots
    if not snapshots:
        return {
            "gapPressure": 1,
            "boundaryPressure": 1,
            "textPressure": 1,
            "actionPressure": 1,
            "surfacePressure": 1,
            "hierarchyFlattening": 1,
            "responsiveStress": 1,
            "consoleErrors": 1,
            "horizontalOverflow": 1,
        }
    worst_gap = max(0.0, max((12 - float(item.metrics.get("actualGap") or 0)) / 12 for item in snapshots))
    worst_boundary = max(0.0, max((16 - float(item.metrics.get("actualPadding") or 0)) / 16 for item in snapshots))
    text_pressure = 1.0 if any(item.metrics.get("primaryClipped") for item in snapshots) else 0.0
    action_pressure = max(
        0.0,
        max(
            (float(item.metrics.get("visibleActions") or 0) - float(item.metrics.get("allowedActions") or 1))
            / max(float(item.metrics.get("allowedActions") or 1), 1)
            for item in snapshots
        ),
    )
    responsive = 1.0 if any(item.metrics.get("horizontalOverflow") and int(item.metrics.get("viewport") or 0) <= 390 for item in snapshots) else 0.0
    return {
        "gapPressure": round(min(worst_gap, 1), 3),
        "boundaryPressure": round(min(worst_boundary, 1), 3),
        "textPressure": text_pressure,
        "actionPressure": round(min(action_pressure, 1), 3),
        "surfacePressure": 0.0,
        "hierarchyFlattening": 0.0,
        "responsiveStress": responsive,
        "consoleErrors": float(sum(int(item.metrics.get("consoleErrors") or 0) for item in snapshots)),
        "horizontalOverflow": float(sum(1 for item in snapshots if item.metrics.get("horizontalOverflow"))),
    }


def _metric_issues(metrics: dict[str, float], contract: dict[str, Any]) -> list[CompressionIssue]:
    issues: list[CompressionIssue] = []
    if metrics["horizontalOverflow"] > 0:
        issues.append(
            CompressionIssue(
                code="HORIZONTAL_OVERFLOW",
                severity="blocker",
                message="horizontal overflow was detected in the render matrix",
                evidence={"count": metrics["horizontalOverflow"]},
            )
        )
    if metrics["consoleErrors"] > 0:
        issues.append(
            CompressionIssue(
                code="CONSOLE_ERROR",
                severity="blocker",
                message="console errors were captured during render",
                evidence={"count": metrics["consoleErrors"]},
            )
        )
    if metrics["actionPressure"] > 0:
        issues.append(
            CompressionIssue(
                code="ACTION_PRESSURE",
                severity="major",
                message="visible actions exceed the contract budget",
                evidence={"pressure": metrics["actionPressure"], "allowed": contract.get("visibleActionBudget")},
            )
        )
    if metrics["textPressure"] > 0:
        issues.append(
            CompressionIssue(
                code="TEXT_PRESSURE",
                severity="blocker",
                message="primary content is clipped or collapsed",
                evidence={"pressure": metrics["textPressure"]},
            )
        )
    return issues


def _score(metrics: dict[str, float], issues: list[CompressionIssue]) -> float:
    score = (
        metrics["gapPressure"] * 0.12
        + metrics["boundaryPressure"] * 0.14
        + metrics["textPressure"] * 0.22
        + metrics["actionPressure"] * 0.22
        + metrics["surfacePressure"] * 0.10
        + metrics["hierarchyFlattening"] * 0.10
        + metrics["responsiveStress"] * 0.10
    )
    if any(issue.severity == "blocker" for issue in issues):
        score = max(score, 0.75)
    return min(score, 1)


def _has_blocker(issues: list[CompressionIssue]) -> bool:
    return any(issue.severity == "blocker" for issue in issues)
