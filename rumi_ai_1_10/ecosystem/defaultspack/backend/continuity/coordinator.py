from __future__ import annotations

from pathlib import Path
from typing import Any

from .checkpoint_builder import CheckpointBuilder
from .credential_envelope import CredentialEnvelopeService
from .errors import ContinuityError, HANDOFF_NOT_FOUND, NODE_NOT_FOUND
from .models import HandoffPlan, content_hash
from .node_registry import NodeRegistry, utc_now
from .operation_store import HandoffOperationStore
from .primary_lease import PrimaryLeaseService
from .provider_portability import ProviderPortabilityService
from .store import JsonFileStore, default_continuity_dir


class ContinuityCoordinator:
    def __init__(self, root: str | Path | None = None, *, sandbox_manager: Any | None = None) -> None:
        self.root = Path(root) if root is not None else default_continuity_dir()
        self.node_registry = NodeRegistry(self.root)
        self.provider_routes = ProviderPortabilityService()
        self.credentials = CredentialEnvelopeService(self.root)
        self.checkpoints = CheckpointBuilder(self.root, sandbox_manager=sandbox_manager)
        self.primary_leases = PrimaryLeaseService(self.root)
        self.operations = HandoffOperationStore(self.root)
        self.restore_store = JsonFileStore(self.root / "restore_records.json")
        self.fallback_store = JsonFileStore(self.root / "provider_fallbacks.json")

    def list_nodes(self) -> dict[str, Any]:
        return {"nodes": self.node_registry.list_nodes(), "local_node": self.node_registry.local_node()}

    def start_pairing(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.node_registry.start_pairing(display_name=str(payload.get("display_name") or ""))

    def accept_pairing(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"node": self.node_registry.accept_pairing(payload)}

    def remove_node(self, node_id: str) -> dict[str, Any]:
        return self.node_registry.remove(node_id)

    def probe_node(self, node_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        node = self.node_registry.get(node_id)
        routes = self.provider_routes.list_routes()
        portable = [route for route in routes if route.get("portable")]
        checks = [
            {"code": "NODE_ONLINE", "ok": bool(node.get("online")), "message": "Node is online." if node.get("online") else "Node is offline."},
            {"code": "RUNTIME_CAPABILITIES", "ok": bool(node.get("sandbox_capabilities")), "capabilities": node.get("sandbox_capabilities") or []},
            {"code": "PROVIDER_ROUTES", "ok": bool(portable), "portable_route_count": len(portable)},
        ]
        return {"node": self.node_registry._public_node(node), "checks": checks, "ok": all(check["ok"] for check in checks)}

    def list_provider_routes(self) -> dict[str, Any]:
        fallbacks = self.fallback_store.read().get("fallbacks", {})
        routes = []
        for route in self.provider_routes.list_routes():
            route_id = str(route.get("route_id") or "")
            configured = fallbacks.get(route_id) if isinstance(fallbacks, dict) else None
            if isinstance(configured, list):
                route["fallback_routes"] = [str(item) for item in configured if str(item or "").strip()]
            routes.append(route)
        return {"routes": routes}

    def set_provider_fallbacks(self, payload: dict[str, Any]) -> dict[str, Any]:
        route_id = str(payload.get("route_id") or "").strip()
        fallback_route_ids = [
            str(item).strip()
            for item in (payload.get("fallback_route_ids") if isinstance(payload.get("fallback_route_ids"), list) else [])
            if str(item or "").strip()
        ]
        known = {str(route.get("route_id") or "") for route in self.provider_routes.list_routes()}
        if route_id not in known:
            raise ContinuityError("Provider route was not found.", "PROVIDER_ROUTE_NOT_FOUND", 404)
        invalid = [item for item in fallback_route_ids if item not in known or item == route_id]
        if invalid:
            raise ContinuityError("Fallback route list contains unknown route IDs.", "NO_ELIGIBLE_FALLBACK_ROUTE", 400, {"invalid_route_ids": invalid})

        def _update(data: dict[str, Any]):
            fallbacks = data.setdefault("fallbacks", {})
            fallbacks[route_id] = fallback_route_ids
            return data, {"route_id": route_id, "fallback_route_ids": fallback_route_ids}

        return self.fallback_store.update(_update)

    def list_provider_extensions(self) -> dict[str, Any]:
        refs = {}
        for route in self.provider_routes.list_routes():
            ref = str(route.get("provider_extension_ref") or "").strip()
            if not ref:
                continue
            refs[ref] = {
                "extension_ref": ref,
                "required_by_routes": sorted([str(route.get("route_id") or "")]),
                "portable": bool(route.get("portable")),
            }
        return {"extensions": sorted(refs.values(), key=lambda item: item["extension_ref"])}

    def probe_provider_route(self, payload: dict[str, Any]) -> dict[str, Any]:
        route = self.provider_routes.resolve(payload)
        destination_id = str(payload.get("destination_node_id") or payload.get("node_id") or "").strip()
        destination = self.node_registry.get(destination_id) if destination_id else self.node_registry.local_node()
        return self.provider_routes.destination_probe(route, destination).as_dict()

    def plan_handoff(self, payload: dict[str, Any]) -> dict[str, Any]:
        route = self.provider_routes.resolve(payload.get("provider_route") if isinstance(payload.get("provider_route"), dict) else payload)
        destination_id = str(payload.get("destination_node_id") or payload.get("node_id") or "").strip()
        if not destination_id:
            nodes = [node for node in self.node_registry.list_nodes() if node.get("destination_kind") != "source"]
            if not nodes:
                raise ContinuityError("No paired destination node is available.", NODE_NOT_FOUND, 404)
            destination_id = str(nodes[0].get("node_id") or "")
        destination = self.node_registry.get(destination_id)
        preflight = self.provider_routes.destination_probe(route, destination)
        sandbox_id = str(payload.get("sandbox_id") or payload.get("seat_id") or "logical-sandbox").strip()
        mode = str(payload.get("mode") or "move").strip() or "move"
        plan = HandoffPlan(
            plan_id="plan-" + content_hash({"sandbox_id": sandbox_id, "destination": destination_id, "route": route.as_dict(), "mode": mode})[:18],
            mode=mode,
            sandbox_id=sandbox_id,
            destination_node_id=destination_id,
            provider_route_ref=route.as_dict(),
            fallback_route_refs=tuple(
                item for item in self.provider_routes.list_routes()
                if item.get("portable") and item.get("route_id") != route.route_id
            )[:3],
            credential_delegation={
                "required": bool(self.provider_routes.secret_for_route(route)),
                "credential_ref": route.credential_ref,
                "plaintext_exported": False,
                "scope": {
                    "provider_id": route.provider_id,
                    "api_id": route.api_id,
                    "allowed_model_ids": list(route.allowed_models or (route.model_id,)),
                    "permissions": ["model.invoke", "api_key.use"],
                    "ttl_seconds": int(payload.get("credential_ttl_seconds") or 3600),
                },
            },
            checkpoint_estimate={
                "mode": "logical_delta",
                "uploads_base_runtime": False,
                "estimated_bytes": 0,
            },
            resource_preflight=preflight.as_dict(),
            cutover={
                "source_remains_primary_until": "destination_runtime_provider_model_and_tool_health_pass",
                "atomic_primary_lease": True,
                "generation_fencing": True,
            },
            status="ready" if preflight.ok else "blocked",
            created_at=utc_now(),
        )
        return {"plan": plan.as_dict()}

    def checkpoint(self, payload: dict[str, Any]) -> dict[str, Any]:
        route = self.provider_routes.resolve(payload.get("provider_route") if isinstance(payload.get("provider_route"), dict) else payload)
        sandbox_id = str(payload.get("sandbox_id") or "logical-sandbox")
        source = self.node_registry.local_node()
        manifest = self.checkpoints.build(
            sandbox_id=sandbox_id,
            source_node_id=str(source.get("node_id") or ""),
            provider_route=route,
            credential_envelope_id=None,
            extra_state=payload.get("state") if isinstance(payload.get("state"), dict) else {},
        )
        operation = self.operations.create(
            {
                "status": "COMPLETED",
                "mode": "checkpoint",
                "sandbox_id": sandbox_id,
                "checkpoint_id": manifest.checkpoint_id,
                "manifest": manifest.as_dict(),
            }
        )
        return {"operation": operation, "checkpoint": manifest.as_dict()}

    def start_handoff(self, payload: dict[str, Any]) -> dict[str, Any]:
        plan = self.plan_handoff(payload)["plan"]
        operation = self.operations.create(
            {
                "mode": plan["mode"],
                "sandbox_id": plan["sandbox_id"],
                "destination_node_id": plan["destination_node_id"],
                "plan": plan,
                "status": "PLANNED",
            }
        )
        operation_id = str(operation["operation_id"])
        operation = self.operations.transition(
            operation_id,
            "PAUSED_USER_ACTION",
            message=(
                "Remote continuity cutover is not enabled in this build. "
                "Source remains primary until authenticated transport, restore, and probe support are available."
            ),
            details={
                "code": "CONTINUITY_REMOTE_HANDOFF_UNAVAILABLE",
                "source_primary": True,
                "destination_primary": False,
                "requires": [
                    "authenticated_remote_transport",
                    "destination_acknowledgement",
                    "remote_restore",
                    "model_probe",
                    "tool_health_check",
                ],
            },
        )
        return {"operation": operation}

    def get_operation(self, operation_id: str) -> dict[str, Any]:
        operation = self.operations.get(operation_id)
        if operation is None:
            raise ContinuityError(f"Handoff operation not found: {operation_id}", HANDOFF_NOT_FOUND, 404)
        return operation

    def list_operations(self) -> dict[str, Any]:
        return {"operations": self.operations.list()}

    def cancel(self, operation_id: str) -> dict[str, Any]:
        operation = self.operations.cancel(operation_id)
        if operation is None:
            raise ContinuityError(f"Handoff operation not found: {operation_id}", HANDOFF_NOT_FOUND, 404)
        return {"operation": operation}

    def retry(self, operation_id: str) -> dict[str, Any]:
        operation = self.get_operation(operation_id)
        plan = operation.get("plan") if isinstance(operation.get("plan"), dict) else {}
        if not plan:
            raise ContinuityError("Handoff operation has no retryable plan.", "HANDOFF_NOT_RETRYABLE", 409)
        return self.start_handoff(
            {
                "sandbox_id": plan.get("sandbox_id"),
                "destination_node_id": plan.get("destination_node_id"),
                "mode": plan.get("mode"),
                "provider_route": plan.get("provider_route_ref"),
            }
        )

    def return_to_device(self, operation_id: str) -> dict[str, Any]:
        operation = self.get_operation(operation_id)
        if str(operation.get("status") or "") == "COMPLETED" and operation.get("returned") is True:
            return {"operation": operation}
        returned = self.operations.transition(
            operation_id,
            "PAUSED_USER_ACTION",
            message="Continuity return cutover is not enabled in this build. Primary lease was not changed.",
            details={"code": "CONTINUITY_REMOTE_HANDOFF_UNAVAILABLE", "source_primary": True},
        )
        return {"operation": returned}

    def _record_restore(self, operation_id: str, manifest: dict[str, Any], destination: dict[str, Any]) -> dict[str, Any]:
        record = {
            "operation_id": operation_id,
            "checkpoint_id": manifest.get("checkpoint_id"),
            "destination_node_id": destination.get("node_id"),
            "destination_kind": destination.get("destination_kind"),
            "restored_at": utc_now(),
            "logical_restore": True,
            "desktop_spec": manifest.get("desktop_spec") or {},
        }

        def _update(data: dict[str, Any]):
            records = data.setdefault("records", {})
            records[operation_id] = record
            return data, dict(record)

        return self.restore_store.update(_update)
