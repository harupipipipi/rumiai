from __future__ import annotations

import platform
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import CHECKPOINT_SECRET_LEAK, ContinuityError
from .models import ContinuityCheckpointManifest, ProviderRouteRef, canonical_json, content_hash
from .store import JsonFileStore, default_continuity_dir


SENSITIVE_MARKERS = ("api_key", "authorization", "bearer", "credential", "password", "private_key", "secret", "token")
SENSITIVE_REFERENCE_KEYS = {
    "credential_envelope_id",
    "credential_ref",
    "provider_route_ref",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _secret_key_present(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            reference_like = lowered in SENSITIVE_REFERENCE_KEYS or lowered.endswith(("_id", "_ref", "_hash"))
            if any(marker in lowered for marker in SENSITIVE_MARKERS) and not reference_like:
                return True
            if _secret_key_present(item):
                return True
    elif isinstance(value, list):
        return any(_secret_key_present(item) for item in value)
    return False


class CheckpointBuilder:
    def __init__(self, root: str | Path | None = None, *, sandbox_manager: Any | None = None) -> None:
        self.root = Path(root) if root is not None else default_continuity_dir()
        self.sandbox_manager = sandbox_manager
        self.store = JsonFileStore(self.root / "checkpoints.json")

    def build(
        self,
        *,
        sandbox_id: str,
        source_node_id: str,
        provider_route: ProviderRouteRef,
        credential_envelope_id: str | None,
        extra_state: dict[str, Any] | None = None,
    ) -> ContinuityCheckpointManifest:
        instance = self._sandbox_instance(sandbox_id)
        if _secret_key_present(instance) or _secret_key_present(extra_state or {}):
            raise ContinuityError("Checkpoint manifest rejected secret-looking keys.", CHECKPOINT_SECRET_LEAK, 500)
        checkpoint_id = "ckpt-" + uuid.uuid4().hex[:18]
        desktop_spec = instance.get("desktop_spec") if isinstance(instance.get("desktop_spec"), dict) else {}
        workspace_binding = instance.get("workspace_binding") if isinstance(instance.get("workspace_binding"), dict) else {}
        workspace_ref = content_hash({"sandbox_id": sandbox_id, "workspace": workspace_binding, "extra": extra_state or {}})
        manifest = ContinuityCheckpointManifest(
            schema_version=1,
            checkpoint_id=checkpoint_id,
            sandbox_id=sandbox_id,
            source_node_id=source_node_id,
            source_generation=int(instance.get("generation") or 1),
            base_runtime_digest=content_hash(
                {
                    "template_id": instance.get("template_id") or "unknown",
                    "provider_id": instance.get("provider_id") or "unknown",
                    "runtime_id": instance.get("runtime_id") or "",
                }
            ),
            template_id=str(instance.get("template_id") or "unknown"),
            architecture=platform.machine() or "unknown",
            workspace_chunk_root=workspace_ref,
            home_overlay_chunk_root=content_hash({"sandbox_id": sandbox_id, "overlay": "logical"}),
            browser_state_ref=None,
            terminal_sessions=tuple(extra_state.get("terminal_sessions", []) if isinstance(extra_state, dict) else []),
            task_state_ref=str((extra_state or {}).get("task_state_ref") or "") or None,
            conversation_state_ref=str((extra_state or {}).get("conversation_state_ref") or "") or None,
            tool_state_ref=str((extra_state or {}).get("tool_state_ref") or "") or None,
            provider_route_ref=provider_route.as_dict(),
            credential_envelope_id=credential_envelope_id,
            desktop_spec=dict(desktop_spec),
            created_at=utc_now(),
            consistency_marker=content_hash({"sandbox_id": sandbox_id, "created_at": utc_now(), "route": provider_route.qualified_route}),
            encryption_metadata={
                "manifest_encrypted": False,
                "chunk_encryption": "destination_scoped_envelope",
                "credential_envelope_id": credential_envelope_id,
            },
        )
        self.save(manifest)
        return manifest

    def save(self, manifest: ContinuityCheckpointManifest) -> None:
        payload = manifest.as_dict()
        if _secret_key_present(payload):
            raise ContinuityError("Checkpoint manifest rejected secret-looking keys.", CHECKPOINT_SECRET_LEAK, 500)

        def _update(data: dict[str, Any]):
            checkpoints = data.setdefault("checkpoints", {})
            checkpoints[manifest.checkpoint_id] = payload
            return data, None

        self.store.update(_update)

    def get(self, checkpoint_id: str) -> dict[str, Any] | None:
        data = self.store.read()
        checkpoints = data.get("checkpoints") if isinstance(data.get("checkpoints"), dict) else {}
        checkpoint = checkpoints.get(str(checkpoint_id))
        return dict(checkpoint) if isinstance(checkpoint, dict) else None

    def _sandbox_instance(self, sandbox_id: str) -> dict[str, Any]:
        if self.sandbox_manager is not None:
            try:
                result = self.sandbox_manager.status(sandbox_id)
                if isinstance(result, dict) and result.get("ok"):
                    return dict(result)
            except Exception:
                pass
            try:
                for item in self.sandbox_manager.list_instances():
                    if str(item.get("sandbox_id") or "") == str(sandbox_id):
                        return dict(item)
            except Exception:
                pass
        return {
            "sandbox_id": sandbox_id,
            "template_id": "checkpoint.logical",
            "provider_id": "unknown",
            "runtime_id": "",
            "generation": 1,
            "desktop_spec": {},
            "workspace_binding": {},
        }
