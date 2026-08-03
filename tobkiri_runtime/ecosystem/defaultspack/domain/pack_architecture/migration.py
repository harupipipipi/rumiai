"""Safe migration inputs for legacy Startup Profiles.

Legacy command strings are retained only as inventory evidence.  They are never
turned into a Shell Provider, never executed, and never used as a production
launch fallback.
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any, Mapping

import yaml  # type: ignore[import-untyped]

from .errors import LegacyMigrationError
from .model import APP_SHELL_CONTRACT, PROFILE_SCHEMA

LEGACY_BASE_PACK_ALIASES = {
    "basepack": "defaults-basepack",
    "defaultspack": "defaults-basepack",
    "defaults": "defaults-basepack",
    "defaults-basepack": "defaults-basepack",
}
KNOWN_SHELL_PROVIDERS = frozenset(
    {"shell.tauri.default", "shell.electron.default", "shell.cli.default"}
)


def migrate_legacy_profile(
    legacy_profile: Mapping[str, Any],
    *,
    known_shell_providers: frozenset[str] = KNOWN_SHELL_PROVIDERS,
) -> dict[str, Any]:
    """Convert a legacy profile into reviewable v4 composition data.

    The returned document is deliberately unresolved when it contains an
    arbitrary ``desktop_app.command``.  A user must choose an exact Shell or
    Application artifact before production activation can proceed.
    """
    if not isinstance(legacy_profile, Mapping):
        raise LegacyMigrationError("legacy profile must be an object")
    profile_id = str(legacy_profile.get("profile_id") or "legacy-migrated").strip()
    if not profile_id:
        raise LegacyMigrationError("legacy profile_id cannot be empty")
    legacy_base = str(
        legacy_profile.get("base_pack") or legacy_profile.get("pack_id") or "defaultspack"
    ).strip()
    base_pack = LEGACY_BASE_PACK_ALIASES.get(legacy_base)
    if base_pack is None:
        raise LegacyMigrationError(
            f"legacy base pack {legacy_base!r} is not a supported migration input"
        )
    launch = legacy_profile.get("launch")
    launch_map = dict(launch) if isinstance(launch, Mapping) else {}
    desktop_app = legacy_profile.get("desktop_app")
    if isinstance(launch_map.get("desktop_app"), Mapping):
        desktop_app = launch_map["desktop_app"]
    desktop_app_map = dict(desktop_app) if isinstance(desktop_app, Mapping) else {}
    command = str(desktop_app_map.get("command") or launch_map.get("command") or "").strip()
    explicit_provider = str(
        launch_map.get("shell_provider")
        or launch_map.get("provider")
        or legacy_profile.get("shell_provider")
        or ""
    ).strip()
    if explicit_provider and explicit_provider not in known_shell_providers:
        raise LegacyMigrationError(
            f"legacy shell provider is not an approved exact provider: {explicit_provider!r}"
        )
    inventory: list[dict[str, Any]] = []
    if command:
        inventory.append(
            {
                "source": "launch.desktop_app.command",
                "command": command,
                "classification": _classify_legacy_command(command),
                "execution": "inventory_only",
                "production_launch": "forbidden",
                "requires": ["human_review", "exact_artifact_variant", "contract_mapping"],
            }
        )
    if launch_map.get("kind"):
        inventory.append(
            {
                "source": "launch.kind",
                "value": str(launch_map.get("kind")),
                "classification": "legacy_launch_kind",
                "execution": "inventory_only",
            }
        )
    migrated: dict[str, Any] = {
        "schema": PROFILE_SCHEMA,
        "profile_id": profile_id,
        "profile_revision": "migration-pending-review",
        "base": {"pack": base_pack, "source": "legacy.base_pack"},
        "packs": _safe_pack_ids(legacy_profile.get("packs")),
        "policy": {
            "network_default": "deny",
            "cloud_keys_optional": True,
            "write_actions_require_approval": True,
            "legacy_commands_executable": False,
        },
        "migration": {
            "source_schema": str(legacy_profile.get("version") or "rumi.profile.v1"),
            "status": "review_required"
            if command or not explicit_provider
            else "shell_selection_required",
            "legacy_inputs": inventory,
            "command_execution": "forbidden",
            "production_fallback": "deny",
        },
    }
    if explicit_provider:
        migrated["shell"] = {
            "contract": APP_SHELL_CONTRACT,
            "provider": explicit_provider,
            "source": "legacy.explicit_shell_provider",
        }
        if not command:
            migrated["migration"]["status"] = "migrated"
    platform_value = legacy_profile.get("platform")
    if isinstance(platform_value, Mapping):
        platform_data = {
            "os": str(platform_value.get("os") or "").strip(),
            "architecture": str(platform_value.get("architecture") or "").strip(),
        }
        if all(platform_data.values()):
            migrated["platform"] = platform_data
    return migrated


def migrate_legacy_profile_file(profile_path: Path) -> dict[str, Any]:
    """Load and migrate a YAML or JSON legacy profile file."""
    try:
        raw = profile_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise LegacyMigrationError(f"cannot read legacy profile {profile_path}: {exc}") from exc
    try:
        document = (
            yaml.safe_load(raw)
            if profile_path.suffix.lower() in {".yaml", ".yml"}
            else json.loads(raw)
        )
    except (ValueError, yaml.YAMLError) as exc:
        raise LegacyMigrationError(f"cannot parse legacy profile {profile_path}: {exc}") from exc
    return migrate_legacy_profile(document)


def _safe_pack_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise LegacyMigrationError("legacy packs must be an array")
    result: list[str] = []
    for item in value:
        pack_id = str(item).strip()
        if not pack_id or any(char.isspace() for char in pack_id):
            raise LegacyMigrationError("legacy pack IDs must be non-empty and whitespace-free")
        if pack_id not in result:
            result.append(pack_id)
    return result


def _classify_legacy_command(command: str) -> str:
    try:
        tokens = [token.lower() for token in shlex.split(command)]
    except ValueError:
        return "malformed_command_inventory"
    normalized = " ".join(tokens)
    if "cargo tauri dev" in normalized or "npm run dev" in normalized:
        return "development_toolchain_candidate"
    if "tauri" in normalized:
        return "standalone_tauri_application_candidate"
    if "electron" in normalized:
        return "standalone_electron_application_candidate"
    if tokens and tokens[0] in {"python", "python3", "node", "deno", "bun"}:
        return "opaque_packaged_process_candidate"
    return "unclassified_legacy_process"
