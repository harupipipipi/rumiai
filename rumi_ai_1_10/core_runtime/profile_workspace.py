from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml


PROFILE_WORKSPACE_VERSION = 1


@dataclass(frozen=True)
class ProfileWorkspacePaths:
    profile_id: str
    root: Path
    profile_file: Path
    user_data_dir: Path
    database_dir: Path
    database_path: Path
    startup_dir: Path
    flows_dir: Path
    prompts_dir: Path
    ecosystem_dir: Path
    permissions_dir: Path
    audit_dir: Path
    snapshots_dir: Path


def _default_user_data_root() -> Path:
    base_dir = Path(__file__).resolve().parent.parent
    configured = os.environ.get("RUMI_USER_DATA")
    return Path(configured) if configured else base_dir / "user_data"


def validate_profile_id(profile_id: str) -> str:
    candidate = str(profile_id or "").strip()
    if not candidate:
        raise ValueError("profile_id must not be empty")
    if "/" in candidate or "\\" in candidate:
        raise ValueError("profile_id must not contain path separators")
    if candidate == ".." or ".." in candidate:
        raise ValueError("profile_id must not contain path traversal segments")
    return candidate


def profile_workspace_payload(paths: ProfileWorkspacePaths) -> dict[str, Any]:
    payload = asdict(paths)
    return {key: str(value) if isinstance(value, Path) else value for key, value in payload.items()}


class ProfileWorkspaceManager:
    def __init__(self, user_data_root: Path | None = None) -> None:
        self.user_data_root = Path(user_data_root) if user_data_root is not None else _default_user_data_root()

    def root_for_profile(self, profile_id: str) -> Path:
        return self.user_data_root / "profiles" / validate_profile_id(profile_id)

    def paths_for_profile(self, profile_id: str) -> ProfileWorkspacePaths:
        safe_id = validate_profile_id(profile_id)
        root = self.root_for_profile(safe_id)
        ecosystem_dir = root / "ecosystem"
        return ProfileWorkspacePaths(
            profile_id=safe_id,
            root=root,
            profile_file=root / "profile.yaml",
            user_data_dir=root / "user_data",
            database_dir=root / "database",
            database_path=root / "database" / "rumi.sqlite",
            startup_dir=root / "startup",
            flows_dir=root / "flows",
            prompts_dir=root / "prompts",
            ecosystem_dir=ecosystem_dir,
            permissions_dir=root / "permissions",
            audit_dir=root / "audit",
            snapshots_dir=ecosystem_dir / "snapshots",
        )

    def initialize_profile_workspace(
        self,
        profile: dict[str, Any],
        *,
        create_missing: bool = True,
    ) -> ProfileWorkspacePaths:
        profile_id = validate_profile_id(str(profile.get("profile_id") or ""))
        paths = self.paths_for_profile(profile_id)
        if not create_missing:
            return paths

        for directory in (
            paths.root,
            paths.user_data_dir,
            paths.database_dir,
            paths.startup_dir,
            paths.flows_dir,
            paths.prompts_dir,
            paths.ecosystem_dir,
            paths.permissions_dir,
            paths.audit_dir,
            paths.snapshots_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        if not paths.profile_file.exists():
            self.save_profile_yaml(profile_id, profile)
        self._write_yaml_if_missing(paths.startup_dir / "launch.yaml", self._startup_launch_defaults(profile))
        self._write_yaml_if_missing(paths.startup_dir / "surface.yaml", self._surface_defaults(profile))
        self._write_yaml_if_missing(
            paths.permissions_dir / "grants.yaml",
            {"version": 1, "profile_id": profile_id, "grants": []},
        )
        self._write_yaml_if_missing(
            paths.permissions_dir / "tool_policy.yaml",
            {
                "version": 1,
                "profile_id": profile_id,
                "network_default": "deny",
                "write_actions_require_approval": True,
                "high_risk_tools_require_approval": True,
                "allow_client_supplied_approved": False,
            },
        )
        self._write_yaml_if_missing(
            paths.permissions_dir / "approvals.yaml",
            {"version": 1, "profile_id": profile_id, "one_shot_tokens": [], "persistent_approvals": []},
        )
        paths.database_path.touch(exist_ok=True)
        (paths.audit_dir / "events.jsonl").touch(exist_ok=True)
        return paths

    def load_profile_yaml(self, profile_id: str) -> dict[str, Any]:
        path = self.paths_for_profile(profile_id).profile_file
        if not path.exists():
            return {}
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}

    def save_profile_yaml(self, profile_id: str, profile: dict[str, Any]) -> None:
        paths = self.paths_for_profile(profile_id)
        paths.root.mkdir(parents=True, exist_ok=True)
        payload = self._profile_yaml_payload(profile_id, profile)
        self._atomic_write_text(paths.profile_file, yaml.safe_dump(payload, allow_unicode=True, sort_keys=False))

    def profile_database_path(self, profile_id: str) -> Path:
        return self.paths_for_profile(profile_id).database_path

    def profile_user_data_dir(self, profile_id: str) -> Path:
        return self.paths_for_profile(profile_id).user_data_dir

    def write_startup_config(self, profile_id: str, config: dict[str, Any]) -> None:
        paths = self.paths_for_profile(profile_id)
        paths.startup_dir.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "profile_id": paths.profile_id, **dict(config)}
        self._atomic_write_text(paths.startup_dir / "launch.yaml", yaml.safe_dump(payload, sort_keys=False))

    def read_startup_config(self, profile_id: str) -> dict[str, Any]:
        path = self.paths_for_profile(profile_id).startup_dir / "launch.yaml"
        if not path.exists():
            return {}
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}

    def payload_for_profile(self, profile_id: str) -> dict[str, Any]:
        return profile_workspace_payload(self.paths_for_profile(profile_id))

    def mark_workspace_orphaned(self, profile_id: str, profile: dict[str, Any] | None = None) -> None:
        paths = self.paths_for_profile(profile_id)
        paths.root.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "profile_id": paths.profile_id,
            "orphaned": True,
            "profile": dict(profile or {}),
        }
        self._atomic_write_text(paths.root / ".orphaned.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    def _profile_yaml_payload(self, profile_id: str, profile: dict[str, Any]) -> dict[str, Any]:
        safe_id = validate_profile_id(profile_id)
        keys = (
            "version",
            "profile_id",
            "name",
            "kind",
            "display_name",
            "locale",
            "base_pack",
            "graph_id",
            "default_flow",
            "default_graph",
            "system_prompt_id",
            "default_prompt_id",
            "capability_profile_id",
            "launch_capability_graph",
            "packs",
            "graph_ports",
            "node_overrides",
            "enabled_nodes",
            "disabled_nodes",
            "node_settings",
            "policy",
            "permissions",
            "surfaces",
            "metadata",
            "created_at",
            "updated_at",
            "last_runtime_profile_key",
        )
        payload = {key: profile[key] for key in keys if key in profile}
        payload.setdefault("version", profile.get("version", PROFILE_WORKSPACE_VERSION))
        payload["profile_id"] = safe_id
        return payload

    def _startup_launch_defaults(self, profile: dict[str, Any]) -> dict[str, Any]:
        return {
            "version": 1,
            "profile_id": validate_profile_id(str(profile.get("profile_id") or "")),
            "base_pack": profile.get("base_pack"),
            "graph_id": profile.get("graph_id"),
            "packs": list(profile.get("packs") or []),
            "node_overrides": dict(profile.get("node_overrides") or {}),
        }

    def _surface_defaults(self, profile: dict[str, Any]) -> dict[str, Any]:
        return {
            "version": 1,
            "profile_id": validate_profile_id(str(profile.get("profile_id") or "")),
            "surfaces": dict(profile.get("surfaces") or {}),
        }

    def _write_yaml_if_missing(self, path: Path, payload: dict[str, Any]) -> None:
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write_text(path, yaml.safe_dump(payload, allow_unicode=True, sort_keys=False))

    def _atomic_write_text(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(text, encoding="utf-8")
        tmp_path.replace(path)
