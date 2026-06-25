from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ..profile_workspace import ProfileWorkspaceManager, validate_profile_id
from .constants import PLAN_SPEC_VERSION
from .models import OperatingProfile
from .provenance import canonical_json, stable_sha256


class OperatingProfilePlanStore:
    def __init__(self, workspace_manager: ProfileWorkspaceManager | None = None) -> None:
        self.workspace_manager = workspace_manager or ProfileWorkspaceManager()

    def create_plan(
        self,
        profile_id: str,
        target_profile: OperatingProfile | Mapping[str, Any],
        *,
        actor: str = "local_user",
        reason: str = "",
    ) -> dict[str, Any]:
        safe_profile_id = validate_profile_id(profile_id)
        target = target_profile if isinstance(target_profile, OperatingProfile) else OperatingProfile.from_dict(target_profile)
        previous = self.load_active_profile(safe_profile_id)
        unsigned = {
            "version": PLAN_SPEC_VERSION,
            "profile_id": safe_profile_id,
            "actor": str(actor),
            "reason": str(reason),
            "target_profile": target.to_dict(),
            "previous_profile": previous.to_dict() if previous else None,
        }
        plan_id = stable_sha256(unsigned)[:24]
        plan = {**unsigned, "plan_id": plan_id}
        return {**plan, "signature": self._signature(plan)}

    def apply_plan(self, plan: Mapping[str, Any]) -> dict[str, Any]:
        self._verify_plan(plan)
        profile_id = validate_profile_id(str(plan.get("profile_id") or ""))
        target = plan.get("target_profile")
        if not isinstance(target, Mapping):
            raise ValueError("plan target_profile must be an object")
        paths = self._paths(profile_id)
        plan_path = self._scoped(paths["plans_dir"] / f"{plan['plan_id']}.json", profile_id)
        active_path = self._scoped(paths["active_path"], profile_id)
        applied_path = self._scoped(paths["applied_path"], profile_id)
        self._atomic_write_json(plan_path, dict(plan))
        self._atomic_write_json(active_path, dict(target))
        self._atomic_write_json(applied_path, {"profile_id": profile_id, "plan_id": plan["plan_id"]})
        return {"applied": True, "profile_id": profile_id, "plan_id": plan["plan_id"], "path": str(active_path)}

    def undo_plan(self, profile_id: str, plan_id: str | None = None) -> dict[str, Any]:
        safe_profile_id = validate_profile_id(profile_id)
        paths = self._paths(safe_profile_id)
        if plan_id is None:
            applied = self._read_json(paths["applied_path"])
            plan_id = str(applied.get("plan_id") or "")
        if not plan_id:
            raise ValueError("plan_id is required for undo")
        plan_path = self._scoped(paths["plans_dir"] / f"{plan_id}.json", safe_profile_id)
        plan = self._read_json(plan_path)
        self._verify_plan(plan)
        previous = plan.get("previous_profile")
        active_path = self._scoped(paths["active_path"], safe_profile_id)
        if isinstance(previous, Mapping):
            self._atomic_write_json(active_path, dict(previous))
        elif active_path.exists():
            active_path.unlink()
        undo_path = self._scoped(paths["undo_path"], safe_profile_id)
        self._atomic_write_json(undo_path, {"profile_id": safe_profile_id, "undone_plan_id": plan_id})
        return {"undone": True, "profile_id": safe_profile_id, "plan_id": plan_id, "path": str(active_path)}

    def load_active_profile(self, profile_id: str) -> OperatingProfile | None:
        path = self._paths(profile_id)["active_path"]
        data = self._read_json(path)
        if not data:
            return None
        return OperatingProfile.from_dict(data)

    def _paths(self, profile_id: str) -> dict[str, Path]:
        safe_profile_id = validate_profile_id(profile_id)
        self.workspace_manager.initialize_profile_workspace({"profile_id": safe_profile_id}, create_missing=True)
        workspace_paths = self.workspace_manager.paths_for_profile(safe_profile_id)
        root = workspace_paths.root / "operating_profile"
        plans_dir = root / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)
        return {
            "root": root,
            "plans_dir": plans_dir,
            "active_path": root / "active.json",
            "applied_path": root / "applied_plan.json",
            "undo_path": root / "last_undo.json",
        }

    def _verify_plan(self, plan: Mapping[str, Any]) -> None:
        if plan.get("version") != PLAN_SPEC_VERSION:
            raise ValueError("unsupported operating profile plan version")
        signature = plan.get("signature")
        unsigned = {key: plan[key] for key in plan if key != "signature"}
        if not isinstance(signature, str) or signature != self._signature(unsigned):
            raise ValueError("operating profile plan signature mismatch")

    def _signature(self, plan_without_signature: Mapping[str, Any]) -> str:
        return stable_sha256({"domain": "operating_profile_plan", "plan": plan_without_signature})

    def _scoped(self, path: Path, profile_id: str) -> Path:
        root = self.workspace_manager.paths_for_profile(profile_id).root.resolve()
        resolved = path.resolve()
        if root != resolved and root not in resolved.parents:
            raise ValueError("operating profile plan path escaped profile workspace")
        return resolved

    def _read_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _atomic_write_json(self, path: Path, payload: Mapping[str, Any]) -> None:
        text = canonical_json(dict(payload)) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(text, encoding="utf-8")
        tmp_path.replace(path)
