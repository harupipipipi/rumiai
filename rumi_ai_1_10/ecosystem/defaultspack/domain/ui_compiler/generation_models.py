from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import SCHEMA_VERSION, utc_now_iso


def _list(value: list[Any] | tuple[Any, ...] | None) -> list[Any]:
    return list(value or [])


@dataclass(frozen=True)
class UIBuildRun:
    run_id: str
    artifact_root: str
    created_at: str = field(default_factory=utc_now_iso)

    @property
    def path(self) -> Path:
        return Path(self.artifact_root)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "runId": self.run_id,
            "artifactRoot": self.artifact_root,
            "createdAt": self.created_at,
        }


@dataclass(frozen=True)
class UIAgentTask:
    task_id: str
    run_id: str
    node_id: str
    candidate_id: str
    kind: str
    prompt: str
    output_dir: str
    allowed_paths: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "taskId": self.task_id,
            "runId": self.run_id,
            "nodeId": self.node_id,
            "candidateId": self.candidate_id,
            "kind": self.kind,
            "prompt": self.prompt,
            "outputDir": self.output_dir,
            "allowedPaths": list(self.allowed_paths),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class UIAgentResult:
    status: str
    task_id: str
    output_dir: str
    message: str = ""
    files: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "status": self.status,
            "taskId": self.task_id,
            "outputDir": self.output_dir,
            "message": self.message,
            "files": list(self.files),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ComponentBundleManifest:
    node_id: str
    candidate_id: str
    implementation_mode: str
    source_files: list[str]
    fixture_files: list[str]
    required_states: list[str]
    allowed_primitives: list[str]
    visible_action_budget: int
    slot_mappings: list[dict[str, Any]] = field(default_factory=list)
    design_intent: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "nodeId": self.node_id,
            "candidateId": self.candidate_id,
            "implementationMode": self.implementation_mode,
            "sourceFiles": list(self.source_files),
            "fixtureFiles": list(self.fixture_files),
            "requiredStates": list(self.required_states),
            "allowedPrimitives": list(self.allowed_primitives),
            "visibleActionBudget": self.visible_action_budget,
            "slotMappings": list(self.slot_mappings),
            "designIntent": dict(self.design_intent),
        }


@dataclass(frozen=True)
class CandidateBundle:
    node_id: str
    candidate_id: str
    root: str
    manifest: ComponentBundleManifest
    agent_result: UIAgentResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "nodeId": self.node_id,
            "candidateId": self.candidate_id,
            "root": self.root,
            "manifest": self.manifest.to_dict(),
            "agentResult": self.agent_result.to_dict(),
        }


@dataclass(frozen=True)
class AcceptedBundle:
    node_id: str
    candidate_id: str
    source_root: str
    manifest: dict[str, Any]
    selection: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "nodeId": self.node_id,
            "candidateId": self.candidate_id,
            "sourceRoot": self.source_root,
            "manifest": dict(self.manifest),
            "selection": dict(self.selection),
        }
