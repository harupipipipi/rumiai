from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from domain.ui_compiler import (
    CandidateBundle,
    CompressionReport,
    SelectionDecision,
    UICompilerArtifactStore,
)


class CandidateSelector:
    def __init__(self, *, store: UICompilerArtifactStore) -> None:
        self.store = store

    def select(
        self,
        *,
        run_id: str,
        node_id: str,
        candidates: list[CandidateBundle],
        inspections: dict[str, CompressionReport],
        run_root: Path,
    ) -> SelectionDecision:
        rejected: list[dict[str, Any]] = []
        eligible: list[tuple[float, CandidateBundle, CompressionReport]] = []
        for bundle in candidates:
            report = inspections.get(bundle.candidate_id)
            if report is None:
                rejected.append({"candidateId": bundle.candidate_id, "reason": "MISSING_INSPECTION", "evidence": {}})
                continue
            if not bundle.agent_result.ok:
                rejected.append(
                    {
                        "candidateId": bundle.candidate_id,
                        "reason": "AGENT_FAILED",
                        "evidence": bundle.agent_result.to_dict(),
                    }
                )
                continue
            if not report.passed:
                first_issue = report.issues[0].code if report.issues else "COMPRESSION_FAILED"
                rejected.append(
                    {
                        "candidateId": bundle.candidate_id,
                        "reason": first_issue,
                        "evidence": report.to_dict(),
                    }
                )
                continue
            eligible.append((report.compression_score, bundle, report))

        if not eligible:
            decision = SelectionDecision(
                node_id=node_id,
                accepted_candidate_id=None,
                rejected=rejected,
                decision={"status": "fail", "reason": "NO_ACCEPTABLE_CANDIDATE"},
            )
            self.store.save_selection_decision(run_id=run_id, node_id=node_id, decision=decision.to_dict())
            return decision

        eligible.sort(key=lambda item: (item[0], _surface_count(item[1]), item[1].candidate_id))
        score, accepted, report = eligible[0]
        accepted_root = run_root / "accepted" / node_id
        if accepted_root.exists():
            shutil.rmtree(accepted_root)
        shutil.copytree(Path(accepted.root), accepted_root)
        decision = SelectionDecision(
            node_id=node_id,
            accepted_candidate_id=accepted.candidate_id,
            rejected=rejected,
            decision={
                "status": "accepted",
                "compressionScore": score,
                "stateCoverage": "complete",
                "renderMatrix": "passed",
                "inspection": report.to_dict(),
            },
        )
        self.store.save_accepted_bundle(
            run_id=run_id,
            node_id=node_id,
            candidate_id=accepted.candidate_id,
            manifest={
                **accepted.manifest.to_dict(),
                "sourceRoot": str(accepted_root),
                "selection": decision.to_dict(),
            },
        )
        self.store.save_selection_decision(run_id=run_id, node_id=node_id, decision=decision.to_dict())
        return decision


def _surface_count(bundle: CandidateBundle) -> int:
    return len([item for item in bundle.manifest.source_files if item.endswith((".tsx", ".jsx"))])
