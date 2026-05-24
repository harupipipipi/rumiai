"""High-level update orchestration for control-panel APIs."""

from __future__ import annotations

from typing import Any, Mapping

from ..pack_seed import utc_now_iso
from .core_update_manager import CoreUpdateError, CoreUpdateManager
from .models import AutoUpdateRunResult, CoreUpdateResult
from .pack_update_manager import OFFICIAL_PACK_IDS, PackUpdateError, PackUpdateManager, normalize_update_preferences


class UpdateOrchestrator:
    def __init__(
        self,
        *,
        pack_manager: PackUpdateManager | None = None,
        core_manager: CoreUpdateManager | None = None,
    ) -> None:
        self.pack_manager = pack_manager or PackUpdateManager()
        self.core_manager = core_manager or CoreUpdateManager()

    def viewer_status(self) -> dict[str, Any]:
        return {
            "target": "viewer",
            "current_version": None,
            "latest_version": None,
            "update_available": False,
            "staged": False,
            "applied": False,
            "restart_required": False,
            "routes_reload_recommended": False,
            "rollback_available": False,
            "backup_dir": None,
            "errors": ["Viewer updates are handled by the Tauri updater in rumi_viewer."],
        }

    def viewer_install(self) -> dict[str, Any]:
        payload = self.viewer_status()
        payload["restart_required"] = True
        return payload

    def core_status(self) -> dict[str, Any]:
        return self.core_manager.check_core().to_dict()

    def core_stage(self, body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        body = body or {}
        try:
            stage = self.core_manager.stage_core(
                version=str(body["version"]) if body.get("version") else None,
                channel=str(body.get("channel") or "stable"),
            )
            return CoreUpdateResult(
                target="core",
                current_version=self.core_manager.current_version(),
                latest_version=str(stage.get("version") or ""),
                staged=True,
                applied=False,
                restart_required=True,
            ).to_dict() | {"stage_id": stage.get("stage_id")}
        except CoreUpdateError as exc:
            return _error_payload("core", str(exc), restart_required=True)

    def core_apply(self, body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        body = body or {}
        try:
            stage_id = body.get("stage_id")
            if stage_id:
                return self.core_manager.apply_staged_core(str(stage_id)).to_dict()
            return self.core_manager.apply_core(
                version=str(body["version"]) if body.get("version") else None,
                channel=str(body.get("channel") or "stable"),
                force=bool(body.get("force", False)),
            ).to_dict()
        except CoreUpdateError as exc:
            return _error_payload("core", str(exc), restart_required=True)

    def packs_status(self, channel: str = "stable") -> dict[str, Any]:
        checks = self.pack_manager.check_all(channel=channel)
        if not checks:
            checks = [self.pack_manager.check_pack("defaultspack", channel=channel)]
        return {"packs": [check.to_dict() for check in checks], "updates": [check.to_dict() for check in checks]}

    def pack_status(self, pack_id: str, channel: str = "stable") -> dict[str, Any]:
        return self.pack_manager.check_pack(pack_id, channel=channel).to_dict()

    def pack_stage(self, pack_id: str, body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        body = body or {}
        try:
            staged = self.pack_manager.stage_pack(
                pack_id,
                version=str(body["version"]) if body.get("version") else None,
                channel=str(body.get("channel") or "stable"),
            )
            return staged.to_dict()
        except (PackUpdateError, Exception) as exc:
            return _error_payload(f"pack:{pack_id}", str(exc), routes_reload_recommended=True)

    def pack_apply(self, pack_id: str, body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        body = body or {}
        try:
            stage_id = body.get("stage_id")
            if stage_id:
                return self.pack_manager.apply_staged_pack(str(stage_id), expected_pack_id=pack_id).to_dict()
            return self.pack_manager.apply_pack(
                pack_id,
                version=str(body["version"]) if body.get("version") else None,
                channel=str(body.get("channel") or "stable"),
                force=bool(body.get("force", False)),
            ).to_dict()
        except (PackUpdateError, Exception) as exc:
            return _error_payload(f"pack:{pack_id}", str(exc), routes_reload_recommended=True)

    def pack_rollback(self, pack_id: str, body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        body = body or {}
        try:
            return self.pack_manager.rollback_pack(
                pack_id,
                version=str(body["version"]) if body.get("version") else None,
            ).to_dict()
        except Exception as exc:
            return _error_payload(f"pack:{pack_id}", str(exc), routes_reload_recommended=True)

    def read_settings(self) -> dict[str, Any]:
        return self.pack_manager.read_update_preferences()

    def write_settings(self, body: Mapping[str, Any]) -> dict[str, Any]:
        current = self.read_settings()
        merged: dict[str, Any] = {**current}
        if isinstance(body.get("auto_update"), Mapping):
            merged["auto_update"] = {**current["auto_update"], **body["auto_update"]}
        if isinstance(body.get("channels"), Mapping):
            merged["channels"] = {**current["channels"], **body["channels"]}
        if "check_interval_hours" in body:
            merged["check_interval_hours"] = body["check_interval_hours"]
        return self.pack_manager.write_update_preferences(normalize_update_preferences(merged))

    def run_auto_updates_once(self, force: bool = False) -> AutoUpdateRunResult:
        settings = self.read_settings()
        auto_update = settings["auto_update"]
        enabled_targets = [
            target
            for target in ("viewer", "core", "official_packs", "third_party_packs")
            if auto_update.get(target) is True
        ]
        if not enabled_targets:
            return AutoUpdateRunResult(
                enabled_targets=[],
                due=False,
                checked_at=settings.get("last_checked_at"),
                results=list(settings.get("last_results") or []),
                skipped_reason="disabled",
            )
        if not force and not self.pack_manager._auto_update_due(settings):
            return AutoUpdateRunResult(
                enabled_targets=enabled_targets,
                due=False,
                checked_at=settings.get("last_checked_at"),
                results=list(settings.get("last_results") or []),
                skipped_reason="interval",
            )

        results: list[dict[str, Any]] = []
        checked_at = utc_now_iso()
        channels = settings["channels"]

        if auto_update.get("viewer") is True:
            results.append({
                "target": "viewer",
                "status": "handled_by_tauri",
                "restart_required": False,
            })

        if auto_update.get("core") is True:
            try:
                core_check = self.core_manager.check_core(channel=str(channels.get("core", "stable")))
                if not core_check.update_available:
                    results.append({**core_check.to_dict(), "status": "up_to_date"})
                else:
                    core_result = self.core_manager.apply_core(channel=str(channels.get("core", "stable")))
                    results.append({**core_result.to_dict(), "status": "applied"})
            except Exception as exc:
                results.append({"target": "core", "status": "error", "error": str(exc), "restart_required": True})

        if auto_update.get("official_packs") is True or auto_update.get("third_party_packs") is True:
            pack_channel = str(channels.get("packs", "stable"))
            for pack_check in self.pack_manager.check_all(channel=pack_channel):
                if pack_check.pack_id not in OFFICIAL_PACK_IDS:
                    results.append({
                        **pack_check.to_dict(),
                        "status": "manual_required" if pack_check.update_available or auto_update.get("third_party_packs") is True else "skipped",
                        "error": "Third-party pack auto-updates are not supported.",
                    })
                    continue
                if auto_update.get("official_packs") is not True:
                    results.append({**pack_check.to_dict(), "status": "skipped"})
                    continue
                if not pack_check.update_available:
                    results.append({**pack_check.to_dict(), "status": "up_to_date"})
                    continue
                try:
                    pack_result = self.pack_manager.apply_pack(pack_check.pack_id, channel=pack_channel)
                    results.append({**pack_result.to_dict(), "status": "applied"})
                except Exception as exc:
                    results.append({**pack_check.to_dict(), "status": "error", "error": str(exc)})

        if auto_update.get("third_party_packs") is True and not any(
            isinstance(item, dict) and str(item.get("target") or "").startswith("pack:")
            and str(item.get("pack_id") or "").strip() not in OFFICIAL_PACK_IDS
            for item in results
        ):
            results.append({
                "target": "third_party_packs",
                "status": "manual_required",
                "error": "Third-party pack auto-updates are not supported.",
            })

        updated = {**settings, "last_checked_at": checked_at, "last_results": results}
        self.pack_manager.write_update_preferences(updated)
        return AutoUpdateRunResult(enabled_targets=enabled_targets, due=True, checked_at=checked_at, results=results)


def _error_payload(
    target: str,
    error: str,
    *,
    restart_required: bool = False,
    routes_reload_recommended: bool = False,
) -> dict[str, Any]:
    return {
        "target": target,
        "current_version": None,
        "latest_version": None,
        "update_available": False,
        "staged": False,
        "applied": False,
        "restart_required": restart_required,
        "routes_reload_recommended": routes_reload_recommended,
        "rollback_available": False,
        "backup_dir": None,
        "errors": [error],
        "error": error,
        "status_code": 400,
    }


_global_orchestrator: UpdateOrchestrator | None = None


def get_update_orchestrator() -> UpdateOrchestrator:
    global _global_orchestrator
    if _global_orchestrator is None:
        _global_orchestrator = UpdateOrchestrator()
    return _global_orchestrator


def reset_update_orchestrator(**kwargs: Any) -> UpdateOrchestrator:
    global _global_orchestrator
    _global_orchestrator = UpdateOrchestrator(**kwargs)
    return _global_orchestrator
