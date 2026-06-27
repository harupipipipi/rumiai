from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from domain.ui_compiler import FoundationCandidate, FoundationSpec, UIAgentTask, UICompilerArtifactStore
from domain.ui_compiler.models import canonical_id

from .agent_backend import UIAgentBackend
from .prompts import foundation_prompt


class FoundationGenerator:
    def __init__(self, *, backend: UIAgentBackend, store: UICompilerArtifactStore) -> None:
        self.backend = backend
        self.store = store

    def generate(
        self,
        *,
        run_id: str,
        run_root: Path,
        count: int,
        context: dict[str, Any] | None = None,
    ) -> list[FoundationCandidate]:
        candidates: list[FoundationCandidate] = []
        for index in range(max(1, count)):
            candidate_id = f"foundation-{index + 1}"
            output_dir = run_root / "foundation" / "candidates" / candidate_id
            task = UIAgentTask(
                task_id=f"{run_id}-foundation-{index + 1}",
                run_id=run_id,
                node_id="foundation",
                candidate_id=candidate_id,
                kind="foundation",
                prompt=foundation_prompt(run_id=run_id, candidate_id=candidate_id),
                output_dir=str(output_dir),
                allowed_paths=[str(output_dir)],
                metadata={"candidateIndex": index},
            )
            self.store.save_agent_task(run_id=run_id, task_id=task.task_id, task=task.to_dict())
            result = self.backend.run_task(task, context)
            if not result.ok:
                self.store.save_foundation_candidate(
                    run_id=run_id,
                    candidate_id=candidate_id,
                    foundation={"candidateId": candidate_id},
                    report={"status": "fail", "agentResult": result.to_dict()},
                )
                continue
            candidate = self._read_candidate(candidate_id, output_dir)
            self.store.save_foundation_candidate(
                run_id=run_id,
                candidate_id=candidate_id,
                foundation=candidate.spec.to_dict(),
                report=candidate.report,
                tokens_css=_read_text(output_dir / "tokens.css"),
                primitive_manifest=_read_json(output_dir / "primitive-manifest.json"),
            )
            candidates.append(candidate)
        return candidates

    def select(self, *, run_id: str, candidates: list[FoundationCandidate]) -> FoundationCandidate:
        if not candidates:
            raise ValueError("no foundation candidates generated")
        accepted = sorted(candidates, key=lambda item: (item.score, item.candidate_id))[0]
        root = Path(accepted.root)
        self.store.save_accepted_foundation(
            run_id=run_id,
            foundation=accepted.spec.to_dict(),
            selection={
                "status": "accepted",
                "acceptedCandidateId": accepted.candidate_id,
                "rejected": [
                    {"candidateId": item.candidate_id, "score": item.score}
                    for item in candidates
                    if item.candidate_id != accepted.candidate_id
                ],
            },
            tokens_css=_read_text(root / "tokens.css"),
            primitive_manifest=_read_json(root / "primitive-manifest.json"),
        )
        return accepted

    @staticmethod
    def _read_candidate(candidate_id: str, output_dir: Path) -> FoundationCandidate:
        payload = _read_json(output_dir / "foundation.json")
        if not payload:
            raise ValueError(f"foundation candidate missing foundation.json: {candidate_id}")
        report = _read_json(output_dir / "report.json") or {"status": "pass", "score": 0.5}
        spec = FoundationSpec(
            candidate_id=canonical_id(str(payload.get("candidateId") or candidate_id)),
            direction=dict(payload.get("direction") or {}),
            typography=dict(payload.get("typography") or {}),
            spacing=dict(payload.get("spacing") or {}),
            color=dict(payload.get("color") or {}),
            surface=dict(payload.get("surface") or {}),
            primitives=list(payload.get("primitives") if isinstance(payload.get("primitives"), list) else []),
        )
        return FoundationCandidate(
            candidate_id=spec.candidate_id,
            root=str(output_dir),
            spec=spec,
            score=float(report.get("score") or 0.5),
            report=report,
        )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""
