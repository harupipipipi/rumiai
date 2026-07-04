from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Mapping, Protocol

from core_runtime.cloudflare.sdk_client import CloudflareSDKAdapter, CloudflareSDKOperationError, _scrub_secret


RUNNER_DEPLOY_CAPABILITY = "cloudflare.runner.deploy"
_WRITE_CAPABILITIES = {
    "cloudflare.worker.write",
    "cloudflare.d1.write",
    "cloudflare.r2.write",
    "cloudflare.queue.write",
    "cloudflare.workflow.write",
}
_READ_CAPABILITIES = {
    "cloudflare.worker.read",
    "cloudflare.d1.read",
    "cloudflare.r2.read",
    "cloudflare.queue.read",
    "cloudflare.workflow.read",
}


class CloudflareProvisioningSDK(Protocol):
    def list_d1_databases(self, *, account_id: str | None = None, per_page: int = 50) -> list[dict[str, Any]]: ...
    def create_d1_database(self, name: str, *, account_id: str | None = None) -> dict[str, Any]: ...
    def list_r2_buckets(self, *, account_id: str | None = None, per_page: int = 50) -> list[dict[str, Any]]: ...
    def create_r2_bucket(self, name: str, *, account_id: str | None = None, location: str | None = None) -> dict[str, Any]: ...
    def list_queues(self, *, account_id: str | None = None, per_page: int = 50) -> list[dict[str, Any]]: ...
    def create_queue(self, name: str, *, account_id: str | None = None, **params: Any) -> dict[str, Any]: ...
    def list_workflows(self, *, account_id: str | None = None, per_page: int = 50) -> list[dict[str, Any]]: ...
    def put_workflow(self, workflow_name: str, *, script_name: str, class_name: str, bindings: list[dict[str, Any]] | None = None, account_id: str | None = None) -> dict[str, Any]: ...
    def get_worker(self, script_name: str, *, account_id: str | None = None) -> dict[str, Any]: ...
    def upload_worker_module(self, script_name: str, *, main_module: str, modules: list[dict[str, Any]] | None = None, bindings: list[dict[str, Any]] | None = None, account_id: str | None = None) -> dict[str, Any]: ...
    def patch_worker_settings(self, script_name: str, *, settings: Mapping[str, Any], account_id: str | None = None) -> dict[str, Any]: ...
    def patch_worker_secrets(self, script_name: str, secrets: Mapping[str, str], *, account_id: str | None = None) -> list[dict[str, Any]]: ...
    def delete_worker(self, script_name: str, *, account_id: str | None = None) -> dict[str, Any]: ...
    def delete_d1_database(self, database_id: str, *, account_id: str | None = None) -> dict[str, Any]: ...
    def delete_r2_bucket(self, name: str, *, account_id: str | None = None) -> dict[str, Any]: ...
    def delete_queue(self, queue_id_or_name: str, *, account_id: str | None = None) -> dict[str, Any]: ...
    def delete_workflow(self, workflow_name: str, *, account_id: str | None = None) -> dict[str, Any]: ...


@dataclass(frozen=True)
class CloudflareRunnerSpec:
    account_id: str
    prefix: str
    worker_name: str
    d1_database_name: str
    r2_bucket_name: str
    queue_name: str
    workflow_name: str
    zone_id: str = ""
    environment: str = "production"
    secrets: Mapping[str, str] | None = None
    stored_resources: Mapping[str, Any] | None = None

    @classmethod
    def from_metadata(
        cls,
        metadata: Mapping[str, Any],
        *,
        installation_id: str = "local",
        env: Mapping[str, str] | None = None,
    ) -> "CloudflareRunnerSpec":
        env = env or {}
        account_id = _first_text(metadata.get("account_id"), env.get("RUMI_CLOUDFLARE_ACCOUNT_ID"), env.get("CLOUDFLARE_ACCOUNT_ID"))
        zone_id = _first_text(metadata.get("zone_id"), env.get("RUMI_CLOUDFLARE_ZONE_ID"), env.get("CLOUDFLARE_ZONE_ID"))
        prefix = _cloudflare_name(
            _first_text(
                metadata.get("runner_prefix"),
                env.get("RUMI_CLOUDFLARE_RUNNER_PREFIX"),
                f"rumi-{installation_id}",
            ),
            max_length=32,
        )
        environment = _cloudflare_name(_first_text(metadata.get("runner_env"), env.get("RUMI_CLOUDFLARE_RUNNER_ENV"), "production"), max_length=24)
        resources = metadata.get("resources") if isinstance(metadata.get("resources"), Mapping) else {}
        return cls(
            account_id=account_id,
            prefix=prefix,
            worker_name=_cloudflare_name(_first_text(resources.get("worker", {}).get("name") if isinstance(resources.get("worker"), Mapping) else "", f"{prefix}-runner"), max_length=63),
            d1_database_name=_cloudflare_name(_first_text(resources.get("d1", {}).get("name") if isinstance(resources.get("d1"), Mapping) else "", f"{prefix}-state"), max_length=63),
            r2_bucket_name=_cloudflare_name(_first_text(resources.get("r2", {}).get("name") if isinstance(resources.get("r2"), Mapping) else "", f"{prefix}-artifacts"), max_length=63),
            queue_name=_cloudflare_name(_first_text(resources.get("queue", {}).get("name") if isinstance(resources.get("queue"), Mapping) else "", f"{prefix}-tasks"), max_length=63),
            workflow_name=_cloudflare_name(_first_text(resources.get("workflow", {}).get("name") if isinstance(resources.get("workflow"), Mapping) else "", f"{prefix}-workflow"), max_length=63),
            zone_id=zone_id,
            environment=environment,
            stored_resources=resources,
        )


class CloudflareRunnerProvisioner:
    def __init__(
        self,
        sdk: CloudflareProvisioningSDK | None = None,
        *,
        api_token: str | None = None,
        capabilities: list[str] | None = None,
        approved_capabilities: list[str] | None = None,
    ) -> None:
        self.sdk = sdk or CloudflareSDKAdapter(api_token=api_token)
        self.capabilities = set(capabilities or [])
        self.approved_capabilities = set(approved_capabilities or [])

    def plan(self, spec: CloudflareRunnerSpec) -> dict[str, Any]:
        resources = _resource_payload(spec)
        status = "missing_account_id" if not spec.account_id else "ready"
        return {
            "success": bool(spec.account_id),
            "status": status,
            "dry_run": True,
            "account_id_configured": bool(spec.account_id),
            "zone_id_configured": bool(spec.zone_id),
            "resources": resources,
            "actions": [
                _action("ensure", "d1", spec.d1_database_name, "cloudflare.d1.write"),
                _action("ensure", "r2", spec.r2_bucket_name, "cloudflare.r2.write"),
                _action("ensure", "queue", spec.queue_name, "cloudflare.queue.write"),
                _action("ensure", "workflow", spec.workflow_name, "cloudflare.workflow.write", optional=True),
                _action("upload", "worker", spec.worker_name, "cloudflare.worker.write"),
                _action("patch", "worker_secrets", spec.worker_name, "cloudflare.worker.write"),
            ],
            "approval_required_capabilities": [RUNNER_DEPLOY_CAPABILITY],
        }

    def deploy(self, spec: CloudflareRunnerSpec, *, dry_run: bool = False) -> dict[str, Any]:
        if dry_run:
            return self.plan(spec)
        guard = self._write_guard(spec)
        if guard:
            return guard

        operations: list[dict[str, Any]] = []
        resources: dict[str, Any] = {}
        status = "deployed"
        last_error = ""

        try:
            d1 = self._ensure_named(
                "d1",
                self.sdk.list_d1_databases,
                lambda: self.sdk.create_d1_database(spec.d1_database_name, account_id=spec.account_id),
                spec.d1_database_name,
                spec.account_id,
                operations,
            )
            resources["d1"] = _compact_resource(d1, fallback_name=spec.d1_database_name)

            r2 = self._ensure_named(
                "r2",
                self.sdk.list_r2_buckets,
                lambda: self.sdk.create_r2_bucket(spec.r2_bucket_name, account_id=spec.account_id),
                spec.r2_bucket_name,
                spec.account_id,
                operations,
            )
            resources["r2"] = _compact_resource(r2, fallback_name=spec.r2_bucket_name)

            queue = self._ensure_named(
                "queue",
                self.sdk.list_queues,
                lambda: self.sdk.create_queue(spec.queue_name, account_id=spec.account_id),
                spec.queue_name,
                spec.account_id,
                operations,
            )
            resources["queue"] = _compact_resource(queue, fallback_name=spec.queue_name)

            try:
                workflow = self._ensure_named(
                    "workflow",
                    self.sdk.list_workflows,
                    lambda: self.sdk.put_workflow(
                        spec.workflow_name,
                        script_name=spec.worker_name,
                        class_name="RumiRunnerWorkflow",
                        bindings=_worker_bindings(spec, resources),
                        account_id=spec.account_id,
                    ),
                    spec.workflow_name,
                    spec.account_id,
                    operations,
                )
                resources["workflow"] = _compact_resource(workflow, fallback_name=spec.workflow_name)
            except Exception as exc:
                status = "degraded"
                last_error = _scrub_secret(str(exc), "")
                resources["workflow"] = {"name": spec.workflow_name, "status": "degraded", "error": last_error}
                operations.append({"resource": "workflow", "operation": "degraded", "name": spec.workflow_name})

            worker = self._upsert_worker(spec, resources, operations)
            resources["worker"] = _compact_resource(worker, fallback_name=spec.worker_name)
            secrets = dict(spec.secrets or {})
            if secrets:
                self.sdk.patch_worker_secrets(spec.worker_name, secrets, account_id=spec.account_id)
            operations.append({"resource": "worker_secrets", "operation": "patched", "name": spec.worker_name, "count": len(secrets)})
        except Exception as exc:
            return {
                "success": False,
                "status": "error",
                "resources": resources,
                "operations": operations,
                "last_error": _scrub_secret(str(exc), ""),
            }

        return {
            "success": True,
            "status": status,
            "resources": resources,
            "operations": operations,
            "last_deployed_at": _now(),
            "last_error": last_error,
        }

    def status(self, spec: CloudflareRunnerSpec) -> dict[str, Any]:
        if not spec.account_id:
            return {**self.plan(spec), "dry_run": False}
        if not self._can_read():
            return {
                "success": False,
                "status": "insufficient_capabilities",
                "resources": _resource_payload(spec),
                "missing_capabilities": sorted(_READ_CAPABILITIES - self.capabilities),
            }
        resources = _resource_payload(spec)
        try:
            resources["worker"] = _compact_resource(self.sdk.get_worker(spec.worker_name, account_id=spec.account_id), fallback_name=spec.worker_name)
            status = "deployed"
        except Exception as exc:
            status = "ready"
            resources["worker"]["status"] = "missing"
            resources["worker"]["last_error"] = _scrub_secret(str(exc), "")
        return {"success": True, "status": status, "resources": resources}

    def delete(self, spec: CloudflareRunnerSpec) -> dict[str, Any]:
        guard = self._write_guard(spec)
        if guard:
            return guard
        operations: list[dict[str, Any]] = []
        for resource, name, remover in (
            ("worker", spec.worker_name, lambda: self.sdk.delete_worker(spec.worker_name, account_id=spec.account_id)),
            ("workflow", spec.workflow_name, lambda: self.sdk.delete_workflow(spec.workflow_name, account_id=spec.account_id)),
            ("queue", spec.queue_name, lambda: self.sdk.delete_queue(spec.queue_name, account_id=spec.account_id)),
            ("r2", spec.r2_bucket_name, lambda: self.sdk.delete_r2_bucket(spec.r2_bucket_name, account_id=spec.account_id)),
            ("d1", _stored_id(spec, "d1") or spec.d1_database_name, lambda: self.sdk.delete_d1_database(_stored_id(spec, "d1") or spec.d1_database_name, account_id=spec.account_id)),
        ):
            if not _rumi_owned(spec, name):
                operations.append({"resource": resource, "operation": "skipped", "name": name, "reason": "not_rumi_owned"})
                continue
            try:
                remover()
                operations.append({"resource": resource, "operation": "deleted", "name": name})
            except Exception as exc:
                operations.append({"resource": resource, "operation": "delete_failed", "name": name, "error": _scrub_secret(str(exc), "")})
        return {"success": True, "status": "deleted", "resources": _resource_payload(spec), "operations": operations}

    def _write_guard(self, spec: CloudflareRunnerSpec) -> dict[str, Any] | None:
        if not spec.account_id:
            return {"success": False, "status": "missing_account_id", "resources": _resource_payload(spec)}
        if RUNNER_DEPLOY_CAPABILITY not in self.capabilities and not _WRITE_CAPABILITIES.issubset(self.capabilities):
            return {
                "success": False,
                "status": "insufficient_capabilities",
                "resources": _resource_payload(spec),
                "missing_capabilities": sorted(_WRITE_CAPABILITIES - self.capabilities),
            }
        if RUNNER_DEPLOY_CAPABILITY not in self.approved_capabilities:
            return {
                "success": False,
                "status": "approval_required",
                "resources": _resource_payload(spec),
                "approval_required": True,
                "approval_required_capabilities": [RUNNER_DEPLOY_CAPABILITY],
            }
        return None

    def _can_read(self) -> bool:
        return RUNNER_DEPLOY_CAPABILITY in self.capabilities or bool(_READ_CAPABILITIES & self.capabilities)

    def _ensure_named(
        self,
        resource: str,
        lister,
        creator,
        name: str,
        account_id: str,
        operations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        existing = _find_named(lister(account_id=account_id), name)
        if existing:
            operations.append({"resource": resource, "operation": "reused", "name": name})
            return existing
        created = creator()
        operations.append({"resource": resource, "operation": "created", "name": name})
        return created

    def _upsert_worker(
        self,
        spec: CloudflareRunnerSpec,
        resources: Mapping[str, Any],
        operations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            existing = self.sdk.get_worker(spec.worker_name, account_id=spec.account_id)
            operation = "updated"
        except CloudflareSDKOperationError:
            existing = {}
            operation = "created"
        worker = self.sdk.upload_worker_module(
            spec.worker_name,
            main_module="index.js",
            modules=[{"name": "index.js", "content_type": "application/javascript+module", "content": _worker_module_source()}],
            bindings=_worker_bindings(spec, resources),
            account_id=spec.account_id,
        )
        self.sdk.patch_worker_settings(spec.worker_name, settings={"compatibility_date": "2026-07-01"}, account_id=spec.account_id)
        operations.append({"resource": "worker", "operation": operation, "name": spec.worker_name})
        return {**existing, **worker, "name": spec.worker_name}


def _worker_module_source() -> str:
    return (
        "export default { async fetch(request, env) { "
        "return Response.json({ ok: true, service: 'rumi-cloudflare-runner' }); "
        "} };"
    )


def _worker_bindings(spec: CloudflareRunnerSpec, resources: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {"type": "d1_database", "name": "RUMI_STATE", "id": _resource_id(resources.get("d1")) or spec.d1_database_name},
        {"type": "r2_bucket", "name": "RUMI_ARTIFACTS", "bucket_name": spec.r2_bucket_name},
        {"type": "queue", "name": "RUMI_TASKS", "queue_name": spec.queue_name},
        {"type": "plain_text", "name": "RUMI_RUNNER_ENV", "text": spec.environment},
    ]


def _action(operation: str, resource: str, name: str, capability: str, *, optional: bool = False) -> dict[str, Any]:
    return {"operation": operation, "resource": resource, "name": name, "capability": capability, "optional": optional}


def _resource_payload(spec: CloudflareRunnerSpec) -> dict[str, Any]:
    return {
        "worker": {"name": spec.worker_name},
        "d1": {"name": spec.d1_database_name},
        "r2": {"name": spec.r2_bucket_name},
        "queue": {"name": spec.queue_name},
        "workflow": {"name": spec.workflow_name},
    }


def _find_named(items: list[dict[str, Any]], name: str) -> dict[str, Any]:
    for item in items:
        if _first_text(item.get("name"), item.get("queue_name"), item.get("bucket_name")) == name:
            return dict(item)
    return {}


def _compact_resource(resource: Any, *, fallback_name: str) -> dict[str, Any]:
    payload = dict(resource) if isinstance(resource, Mapping) else {}
    return {
        key: value
        for key, value in {
            "id": _resource_id(payload),
            "name": _first_text(payload.get("name"), payload.get("queue_name"), payload.get("bucket_name"), fallback_name),
            "status": _first_text(payload.get("status"), "ready"),
        }.items()
        if value
    }


def _resource_id(resource: Any) -> str:
    if not isinstance(resource, Mapping):
        return ""
    return _first_text(resource.get("id"), resource.get("uuid"), resource.get("database_id"))


def _stored_id(spec: CloudflareRunnerSpec, resource: str) -> str:
    stored = spec.stored_resources if isinstance(spec.stored_resources, Mapping) else {}
    item = stored.get(resource)
    return _resource_id(item) if isinstance(item, Mapping) else ""


def _rumi_owned(spec: CloudflareRunnerSpec, name: str) -> bool:
    text = str(name or "").strip()
    return bool(text and (text.startswith(spec.prefix) or text.startswith("rumi-")))


def _cloudflare_name(value: str, *, max_length: int) -> str:
    text = re.sub(r"[^a-z0-9-]+", "-", str(value or "").strip().lower()).strip("-")
    text = re.sub(r"-+", "-", text)
    return (text or "rumi")[:max_length].strip("-") or "rumi"


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
