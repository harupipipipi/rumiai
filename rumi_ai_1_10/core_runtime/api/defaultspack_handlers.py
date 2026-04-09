"""defaultspack HTTP handlers."""

from __future__ import annotations

from typing import Any, Dict

from ..defaultspack_runtime import invoke_defaultspack_function


class DefaultspackHandlersMixin:
    def _defaultspack_list_modules(self) -> Dict[str, Any]:
        return invoke_defaultspack_function("defaultspack:list_modules")

    def _defaultspack_get_module(self, module_id: str) -> Dict[str, Any]:
        return invoke_defaultspack_function(
            "defaultspack:get_module", {"module_id": module_id}
        )

    def _defaultspack_enable_module(self, module_id: str) -> Dict[str, Any]:
        return invoke_defaultspack_function(
            "defaultspack:set_module_state",
            {"module_id": module_id, "state": "enabled"},
        )

    def _defaultspack_disable_module(self, module_id: str) -> Dict[str, Any]:
        return invoke_defaultspack_function(
            "defaultspack:set_module_state",
            {"module_id": module_id, "state": "disabled"},
        )

    def _defaultspack_reload_module(self, module_id: str) -> Dict[str, Any]:
        return invoke_defaultspack_function(
            "defaultspack:set_module_state",
            {"module_id": module_id, "state": "enabled", "reason": "manual_reload"},
        )

    def _defaultspack_rollback_module(self, module_id: str) -> Dict[str, Any]:
        return invoke_defaultspack_function(
            "defaultspack:set_module_state",
            {"module_id": module_id, "state": "disabled", "reason": "manual_rollback"},
        )

    def _defaultspack_list_setup_packs(self) -> Dict[str, Any]:
        return invoke_defaultspack_function("defaultspack:list_setup_packs")

    def _defaultspack_install_setup_pack(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return invoke_defaultspack_function(
            "defaultspack:install_setup_pack",
            {"setup_pack_id": body.get("setup_pack_id", "")},
        )

    def _defaultspack_grant_all_ok(self, setup_pack_id: str) -> Dict[str, Any]:
        return invoke_defaultspack_function(
            "defaultspack:grant_all_ok", {"setup_pack_id": setup_pack_id}
        )

    def _defaultspack_revoke_all_ok(self, setup_pack_id: str) -> Dict[str, Any]:
        return invoke_defaultspack_function(
            "defaultspack:revoke_all_ok", {"setup_pack_id": setup_pack_id}
        )

    def _defaultspack_get_migration_status(self) -> Dict[str, Any]:
        return invoke_defaultspack_function("defaultspack:get_migration_status")
