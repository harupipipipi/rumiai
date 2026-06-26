from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from .models import COMPILER_VERSION, SCHEMA_VERSION, ComponentContract, UICompilerConfig, UIPlan, canonical_id


class UICompilerArtifactStore:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or (Path.cwd() / ".rumi" / "ui")).resolve()

    def ensure_layout(self) -> dict[str, str]:
        paths = {
            "root": self.root,
            "constitutions": self.root / "constitutions",
            "runs": self.root / "runs",
            "staging": self.root / "runs" / ".staging",
        }
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
        return {key: str(path) for key, path in paths.items()}

    def save_constitution(self, config: UICompilerConfig | dict[str, Any]) -> dict[str, str]:
        self.ensure_layout()
        payload = config.to_dict() if isinstance(config, UICompilerConfig) else dict(config)
        digest = _hash_payload(payload)
        path = self.root / "constitutions" / f"{digest}.json"
        if not path.exists():
            _atomic_write_json(path, payload)
        return {
            "hash": digest,
            "relativePath": _relative_to_root(path, self.root),
        }

    def save_plan(self, plan: UIPlan, *, idempotency_key: str | None = None) -> dict[str, Any]:
        if not plan.is_executable():
            raise ValueError("only executable UI plans can be saved")
        run_id = canonical_id(plan.run_id)
        self.ensure_layout()
        constitution = self.save_constitution(plan.config)
        run_root = self.root / "runs" / run_id
        lock_path = self.root / "runs" / f"{run_id}.lock"
        lock_fd = _acquire_lock(lock_path)
        staging = self.root / "runs" / ".staging" / f"{run_id}-{uuid.uuid4().hex}"
        try:
            if run_root.exists():
                raise FileExistsError(f"UI compiler run already exists: {run_id}")
            staging.mkdir(parents=True)
            (staging / "contracts").mkdir()

            blueprint = plan.to_dict()
            contract_paths = [
                self._write_staged_contract(staging, contract)
                for contract in plan.contracts()
            ]
            _write_json(staging / "blueprint.json", blueprint)
            report = {
                "schemaVersion": SCHEMA_VERSION,
                "runId": run_id,
                "createdAt": plan.created_at,
                "summary": blueprint["summary"],
                "diagnostics": [item.to_dict() for item in plan.diagnostics],
            }
            _write_json(staging / "report.json", report)
            plan_hash = _hash_payload(blueprint)
            manifest = {
                "schemaVersion": SCHEMA_VERSION,
                "compilerVersion": COMPILER_VERSION,
                "runId": run_id,
                "constitutionHash": constitution["hash"],
                "planHash": plan_hash,
                "status": "valid",
                "idempotencyKey": idempotency_key,
                "files": {
                    "blueprint": "blueprint.json",
                    "report": "report.json",
                    "contracts": contract_paths,
                },
            }
            _write_json(staging / "manifest.json", manifest)
            _fsync_tree(staging)
            staging.rename(run_root)
            _fsync_dir(self.root / "runs")
        except Exception:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            raise
        finally:
            os.close(lock_fd)
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass

        return {
            "artifactId": f"run/{run_id}",
            "relativePath": _relative_to_root(run_root, self.root.parent.parent),
            "runId": run_id,
            "constitutionHash": constitution["hash"],
            "planHash": plan_hash,
            "manifest": _relative_to_root(run_root / "manifest.json", self.root.parent.parent),
            "blueprint": _relative_to_root(run_root / "blueprint.json", self.root.parent.parent),
            "report": _relative_to_root(run_root / "report.json", self.root.parent.parent),
            "contracts": [
                _relative_to_root(run_root / rel_path, self.root.parent.parent)
                for rel_path in contract_paths
            ],
        }

    def save_candidate_manifest(
        self,
        *,
        run_id: str,
        node_id: str,
        candidate_id: str,
        manifest: dict[str, Any],
    ) -> str:
        run_segment = canonical_id(run_id)
        node_segment = canonical_id(node_id)
        candidate_segment = canonical_id(candidate_id)
        path = self.root / "runs" / run_segment / "candidates" / node_segment / f"{candidate_segment}.json"
        _atomic_write_json(path, dict(manifest))
        return _relative_to_root(path, self.root.parent.parent)

    def save_accepted_bundle(
        self,
        *,
        run_id: str,
        node_id: str,
        candidate_id: str,
        manifest: dict[str, Any],
    ) -> str:
        run_segment = canonical_id(run_id)
        node_segment = canonical_id(node_id)
        payload = dict(manifest)
        payload["nodeId"] = node_id
        payload["candidateId"] = candidate_id
        path = self.root / "runs" / run_segment / "accepted" / f"{node_segment}.json"
        _atomic_write_json(path, payload)
        return _relative_to_root(path, self.root.parent.parent)

    def _write_staged_contract(self, staging: Path, contract: ComponentContract) -> str:
        contract_id = canonical_id(contract.id)
        relative = Path("contracts") / f"{contract_id}.json"
        _write_json(staging / relative, contract.to_dict())
        return str(relative)


def _acquire_lock(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
    except FileExistsError as exc:
        raise FileExistsError(f"UI compiler run is already being written: {path.stem}") from exc


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        _write_json(tmp_path, payload)
        os.replace(tmp_path, path)
        _fsync_dir(path.parent)
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_tree(path: Path) -> None:
    for child in sorted(path.rglob("*")):
        if child.is_file():
            with child.open("rb") as handle:
                os.fsync(handle.fileno())
        elif child.is_dir():
            _fsync_dir(child)
    _fsync_dir(path)


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _hash_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _relative_to_root(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))
