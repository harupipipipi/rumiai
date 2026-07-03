from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_DEPLOY_CAPABILITY = "cloudflare.runner.deploy"
_DELETE_CAPABILITY = "cloudflare.runner.delete"


@dataclass(frozen=True)
class CloudflareRunnerSpec:
    account_id: str
    prefix: str = "rumi-runner"
    worker_name: str = ""
    d1_database_name: str = ""
    r2_bucket_name: str = ""
    queue_name: str = ""
    workflow_name: str = ""
    zone_id: str = ""
    environment: str = "production"

    def normalized(self) -> "CloudflareRunnerSpec":
        prefix = _safe_name(self.prefix or "rumi-runner")
        return CloudflareRunnerSpec(
            account_id=str(self.account_id or "").strip(),
            prefix=prefix,
            worker_name=_safe_name(self.worker_name or f"{prefix}-worker"),
            d1_database_name=_safe_name(self.d1_database_name or f"{prefix}-d1"),
            r2_bucket_name=_safe_name(self.r2_bucket_name or f"{prefix}-artifacts"),
            queue_name=_safe_name(self.queue_name or f"{prefix}-queue"),
            workflow_name=_safe_name(self.workflow_name or f"{prefix}-workflow"),
            zone_id=str(self.zone_id or "").strip(),
            environment=str(self.environment or "production").strip() or "production",
        )


class CloudflareRunnerProvisioner:
    """Idempotent runner resource planner with explicit dry-run/write separation."""

    def __init__(self, client: Any, *, capabilities: list[str] | tuple[str, ...] | set[str] | None = None) -> None:
        self._client = client
        self._capabilities = {str(item) for item in capabilities or []}

    def plan(self, spec: CloudflareRunnerSpec) -> dict[str, Any]:
        spec = spec.normalized()
        resources = _resources(spec)
        blockers: list[dict[str, str]] = []
        if not spec.account_id:
            blockers.append({"code": "missing_account_id", "message": "Cloudflare account_id is required"})
        return {
            "schema": "rumi.cloudflare.runner.plan.v1",
            "status": "blocked" if blockers else "ready",
            "dry_run": True,
            "account_id": spec.account_id,
            "environment": spec.environment,
            "resources": resources,
            "actions": _actions(resources),
            "blockers": blockers,
            "requires_capabilities": [_DEPLOY_CAPABILITY],
        }

    def status(self, spec: CloudflareRunnerSpec) -> dict[str, Any]:
        spec = spec.normalized()
        plan = self.plan(spec)
        if plan["blockers"]:
            return {**plan, "status": "blocked", "dry_run": False}
        checks = {
            "d1": _safe_get(lambda: self._client.list_d1_databases(account_id=spec.account_id)),
            "r2": _safe_get(lambda: self._client.get_r2_bucket(spec.r2_bucket_name, account_id=spec.account_id)),
            "queue": _safe_get(lambda: self._client.get_queue(spec.queue_name, account_id=spec.account_id)),
            "workflow": _safe_get(lambda: self._client.get_workflow(spec.workflow_name, account_id=spec.account_id)),
            "worker": _safe_get(lambda: self._client.get_worker(spec.worker_name, account_id=spec.account_id)),
        }
        deployed = all(item.get("ok") for item in checks.values())
        return {
            **plan,
            "dry_run": False,
            "status": "deployed" if deployed else "degraded",
            "checks": checks,
        }

    def deploy(self, spec: CloudflareRunnerSpec, *, dry_run: bool = False) -> dict[str, Any]:
        spec = spec.normalized()
        plan = self.plan(spec)
        if plan["blockers"]:
            return plan
        if dry_run:
            return plan
        if _DEPLOY_CAPABILITY not in self._capabilities:
            return {
                **plan,
                "status": "blocked",
                "dry_run": False,
                "blockers": [
                    {"code": "insufficient_capabilities", "message": f"{_DEPLOY_CAPABILITY} is required"}
                ],
            }

        results: list[dict[str, Any]] = []
        results.append({"resource": "d1", "result": self._ensure_d1(spec)})
        results.append({"resource": "r2", "result": self._ensure_r2(spec)})
        results.append({"resource": "queue", "result": self._ensure_queue(spec)})
        results.append({"resource": "workflow", "result": self._ensure_workflow(spec)})
        results.append({"resource": "worker", "result": self._ensure_worker(spec)})
        results.append({"resource": "secrets", "result": self._patch_worker_secrets(spec)})
        return {**plan, "status": "deployed", "dry_run": False, "results": results}

    def delete(self, spec: CloudflareRunnerSpec) -> dict[str, Any]:
        spec = spec.normalized()
        plan = self.plan(spec)
        if plan["blockers"]:
            return plan
        if _DELETE_CAPABILITY not in self._capabilities and _DEPLOY_CAPABILITY not in self._capabilities:
            return {
                **plan,
                "status": "blocked",
                "dry_run": False,
                "blockers": [
                    {"code": "insufficient_capabilities", "message": f"{_DELETE_CAPABILITY} is required"}
                ],
            }
        if not all(_owned_by_prefix(name, spec.prefix) for name in _resources(spec).values()):
            return {
                **plan,
                "status": "blocked",
                "dry_run": False,
                "blockers": [{"code": "resource_not_owned", "message": "Refusing to delete non-Rumi-prefixed resources"}],
            }
        results = [
            {"resource": "worker", "result": _safe_get(lambda: self._client.delete_worker(spec.worker_name, account_id=spec.account_id))},
            {"resource": "workflow", "result": _safe_get(lambda: self._client.delete_workflow(spec.workflow_name, account_id=spec.account_id))},
            {"resource": "queue", "result": _safe_get(lambda: self._client.delete_queue(spec.queue_name, account_id=spec.account_id))},
            {"resource": "r2", "result": _safe_get(lambda: self._client.delete_r2_bucket(spec.r2_bucket_name, account_id=spec.account_id))},
        ]
        d1 = _safe_get(lambda: self._client.get_d1_database(spec.d1_database_name, account_id=spec.account_id))
        database_id = str((d1.get("value") or {}).get("uuid") or (d1.get("value") or {}).get("id") or spec.d1_database_name)
        results.append(
            {"resource": "d1", "result": _safe_get(lambda: self._client.delete_d1_database(database_id, account_id=spec.account_id))}
        )
        return {**plan, "status": "deleted", "dry_run": False, "results": results}

    def _ensure_d1(self, spec: CloudflareRunnerSpec) -> dict[str, Any]:
        existing = _find_named(self._client.list_d1_databases(account_id=spec.account_id), spec.d1_database_name)
        return existing or self._client.create_d1_database(spec.d1_database_name, account_id=spec.account_id)

    def _ensure_r2(self, spec: CloudflareRunnerSpec) -> dict[str, Any]:
        existing = _safe_get(lambda: self._client.get_r2_bucket(spec.r2_bucket_name, account_id=spec.account_id))
        if existing.get("ok"):
            return dict(existing.get("value") or {})
        return self._client.create_r2_bucket(spec.r2_bucket_name, account_id=spec.account_id)

    def _ensure_queue(self, spec: CloudflareRunnerSpec) -> dict[str, Any]:
        existing = _safe_get(lambda: self._client.get_queue(spec.queue_name, account_id=spec.account_id))
        if existing.get("ok"):
            return dict(existing.get("value") or {})
        return self._client.create_queue(spec.queue_name, account_id=spec.account_id)

    def _ensure_workflow(self, spec: CloudflareRunnerSpec) -> dict[str, Any]:
        existing = _safe_get(lambda: self._client.get_workflow(spec.workflow_name, account_id=spec.account_id))
        if existing.get("ok"):
            return dict(existing.get("value") or {})
        return self._client.put_workflow(
            spec.workflow_name,
            script_name=spec.worker_name,
            class_name="RumiWorkflow",
            bindings={},
            account_id=spec.account_id,
        )

    def _ensure_worker(self, spec: CloudflareRunnerSpec) -> dict[str, Any]:
        return self._client.upload_worker_module(
            spec.worker_name,
            main_module="worker.js",
            modules=[{"name": "worker.js", "content": "export default { fetch() { return new Response('ok') } };"}],
            bindings={
                "d1_database_name": spec.d1_database_name,
                "r2_bucket_name": spec.r2_bucket_name,
                "queue_name": spec.queue_name,
                "workflow_name": spec.workflow_name,
            },
            account_id=spec.account_id,
        )

    def _patch_worker_secrets(self, spec: CloudflareRunnerSpec) -> list[dict[str, Any]]:
        return self._client.patch_worker_secrets(spec.worker_name, {}, account_id=spec.account_id)


def _safe_name(value: str) -> str:
    text = re.sub(r"[^a-z0-9-]+", "-", str(value or "").strip().lower()).strip("-")
    return re.sub(r"-+", "-", text)[:63] or "rumi-runner"


def _owned_by_prefix(name: str, prefix: str) -> bool:
    clean_prefix = _safe_name(prefix)
    return str(name or "").startswith(clean_prefix)


def _resources(spec: CloudflareRunnerSpec) -> dict[str, str]:
    return {
        "worker": spec.worker_name,
        "d1": spec.d1_database_name,
        "r2": spec.r2_bucket_name,
        "queue": spec.queue_name,
        "workflow": spec.workflow_name,
    }


def _actions(resources: dict[str, str]) -> list[dict[str, str]]:
    return [{"action": "ensure", "resource": kind, "name": name} for kind, name in resources.items()]


def _safe_get(callback) -> dict[str, Any]:
    try:
        return {"ok": True, "value": callback()}
    except Exception as exc:
        return {"ok": False, "error": _redacted_error(exc)}


def _redacted_error(exc: Exception) -> str:
    text = str(exc)
    return re.sub(r"(Bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[redacted]", text)


def _find_named(items: Any, name: str) -> dict[str, Any]:
    for item in items or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("name") or item.get("database_name") or item.get("queue_name") or "") == name:
            return dict(item)
    return {}
