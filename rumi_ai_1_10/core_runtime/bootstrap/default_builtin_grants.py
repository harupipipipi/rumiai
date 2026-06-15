"""Default built-in grants for Authority and host capability mediation."""

from __future__ import annotations

import os
from typing import Any


AUTHORITY_WINDOW_PRINCIPAL = "system:authority-approval-window"
HOST_CAPABILITY_BROKER_PRINCIPAL = "system:host-capability-broker"
HOST_CAPABILITIES_PACK_ID = "rumi_host_capabilities_pack"


AUTHORITY_WINDOW_PERMISSIONS = (
    "authority.request.read",
    "authority.request.list",
    "authority.request.approve",
    "authority.request.deny",
    "authority.host_intent.approve",
    "authority.host_intent.deny",
)

HOST_BROKER_PERMISSIONS = (
    "host.permission.status",
    "host.permission.open_settings",
    "host.intent.execute",
    "host.stream.start",
    "host.stream.stop",
)

HOST_CAPABILITIES_PACK_PERMISSIONS = (
    "function.call",
    "host.permission.status",
    "host.permission.open_settings",
    "host.screen.capture",
    "host.accessibility.read",
    "host.accessibility.mutate",
    "host.input.pointer",
    "host.input.keyboard",
    "host.clipboard.read",
    "host.clipboard.write",
    "host.microphone.capture",
    "host.audio.capture",
    "host.audio.output",
    "host.speech.transcribe",
    "host.speech.synthesize",
    "host.camera.capture",
    "host.file.open_dialog",
    "host.file.read_user_selected",
    "host.file.write_user_selected",
    "host.process.open_url",
    "host.process.launch_app",
)


DEFAULT_BUILTIN_GRANTS: tuple[dict[str, Any], ...] = (
    {
        "principal_id": AUTHORITY_WINDOW_PRINCIPAL,
        "permission_ids": AUTHORITY_WINDOW_PERMISSIONS,
        "config": {"mode": "builtin"},
    },
    {
        "principal_id": HOST_CAPABILITY_BROKER_PRINCIPAL,
        "permission_ids": HOST_BROKER_PERMISSIONS,
        "config": {"mode": "builtin"},
    },
    {
        "principal_id": HOST_CAPABILITIES_PACK_ID,
        "permission_ids": HOST_CAPABILITIES_PACK_PERMISSIONS,
        "config": {"mode": "builtin", "allow_stream": True},
    },
)


def default_builtin_grants_enabled() -> bool:
    if os.environ.get("RUMI_DISABLE_DEFAULT_HOST_GRANTS") in {"1", "true", "TRUE"}:
        return False
    if os.environ.get("RUMI_DISABLE_AUTHORITY_WINDOW") in {"1", "true", "TRUE"}:
        return False
    if str(os.environ.get("RUMI_SECURITY_MODE") or "").strip().lower() in {"strict", "strict_untrusted"}:
        return False
    return True


def apply_default_builtin_grants(grant_manager: Any) -> list[dict[str, Any]]:
    if not default_builtin_grants_enabled():
        return []
    if grant_manager is None or not callable(getattr(grant_manager, "grant_permission", None)):
        return []
    applied: list[dict[str, Any]] = []
    for record in DEFAULT_BUILTIN_GRANTS:
        principal_id = str(record["principal_id"])
        config: dict[str, Any] = dict(record.get("config") or {})
        raw_permission_ids = record.get("permission_ids")
        if not isinstance(raw_permission_ids, (list, tuple, set, frozenset)):
            continue
        for permission_id in raw_permission_ids:
            if permission_id == "host.process.exec_guarded":
                continue
            grant_manager.grant_permission(principal_id, permission_id, config)
            applied.append({"principal_id": principal_id, "permission_id": permission_id})
    return applied
