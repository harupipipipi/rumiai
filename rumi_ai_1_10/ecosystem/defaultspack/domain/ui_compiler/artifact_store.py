from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import ComponentContract, UICompilerConfig, UIPlan


_ARTIFACT_DIRS = [
    "foundation",
    "blueprints",
    "contracts",
    "candidates",
    "accepted",
    "renders",
    "reports",
]


class UICompilerArtifactStore:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or (Path.cwd() / ".rumi" / "ui")).resolve()

    def ensure_layout(self) -> dict[str, str]:
        self.root.mkdir(parents=True, exist_ok=True)
        paths = {"root": str(self.root)}
        for dirname in _ARTIFACT_DIRS:
            path = self.root / dirname
            path.mkdir(parents=True, exist_ok=True)
            paths[dirname] = str(path)
        return paths

    def save_constitution(self, config: UICompilerConfig | dict[str, Any]) -> str:
        payload = config.to_dict() if isinstance(config, UICompilerConfig) else dict(config)
        return self._write_json(Path("constitution.json"), payload)

    def save_plan(self, plan: UIPlan) -> dict[str, Any]:
        self.ensure_layout()
        constitution_path = self.save_constitution(plan.config)
        blueprint_path = self._write_json(
            Path("blueprints") / f"{_safe_segment(plan.run_id)}.json",
            plan.to_dict(),
        )
        contract_paths = [self.save_contract(contract) for contract in plan.contracts()]
        report_path = self._write_json(
            Path("reports") / f"{_safe_segment(plan.run_id)}-plan-report.json",
            {
                "runId": plan.run_id,
                "createdAt": plan.created_at,
                "summary": plan.to_dict()["summary"],
                "diagnostics": [item.to_dict() for item in plan.diagnostics],
            },
        )
        return {
            "root": str(self.root),
            "constitution": constitution_path,
            "blueprint": blueprint_path,
            "contracts": contract_paths,
            "report": report_path,
        }

    def save_contract(self, contract: ComponentContract) -> str:
        return self._write_json(
            Path("contracts") / f"{_safe_segment(contract.id)}.json",
            contract.to_dict(),
        )

    def save_candidate_manifest(
        self,
        *,
        node_id: str,
        candidate_id: str,
        manifest: dict[str, Any],
    ) -> str:
        return self._write_json(
            Path("candidates") / _safe_segment(node_id) / f"{_safe_segment(candidate_id)}.json",
            manifest,
        )

    def save_accepted_bundle(
        self,
        *,
        node_id: str,
        candidate_id: str,
        manifest: dict[str, Any],
    ) -> str:
        payload = dict(manifest)
        payload.setdefault("nodeId", node_id)
        payload.setdefault("candidateId", candidate_id)
        return self._write_json(
            Path("accepted") / f"{_safe_segment(node_id)}.json",
            payload,
        )

    def _write_json(self, relative_path: Path, payload: dict[str, Any]) -> str:
        path = (self.root / relative_path).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("artifact path must stay under the UI artifact root") from exc
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return str(path)


def _safe_segment(value: str) -> str:
    raw = str(value or "").strip()
    if not raw or raw in {".", ".."} or "/" in raw or "\\" in raw:
        raise ValueError("artifact id must be a single path segment")
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("-._")
    if not safe or safe in {".", ".."}:
        raise ValueError("artifact id must contain a safe filename character")
    return safe
