from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
import importlib
import importlib.util
import json
from typing import Any
import urllib.error
import urllib.parse
import urllib.request


_CLOUDFLARE_PAGES_MAX_PAGE_SIZE = 10
_CLOUDFLARE_API_BASE_URL = "https://api.cloudflare.com/client/v4"


@dataclass(frozen=True)
class CloudflareSDKStatus:
    available: bool
    status: str
    package: str = "cloudflare"
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "status": self.status,
            "package": self.package,
            "detail": self.detail,
        }


class CloudflareSDKOperationError(RuntimeError):
    def __init__(self, message: str, *, error_type: str = "", status_code: int | None = None) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": "cloudflare_sdk_operation_failed",
            "message": str(self),
            "error_type": self.error_type,
            "status_code": self.status_code,
        }


def cloudflare_sdk_status() -> dict[str, Any]:
    if importlib.util.find_spec("cloudflare") is None:
        return CloudflareSDKStatus(
            available=False,
            status="sdk_missing",
            detail="Install the official Cloudflare Python SDK to enable provisioning.",
        ).to_dict()
    return CloudflareSDKStatus(
        available=True,
        status="ready",
        detail="Cloudflare Python SDK is importable.",
    ).to_dict()


class CloudflareSDKAdapter:
    def __init__(self, *, api_token: str | None = None, account_id: str | None = None) -> None:
        self._api_token = str(api_token or "").strip()
        self._account_id = str(account_id or "").strip()

    def status(self) -> dict[str, Any]:
        status = cloudflare_sdk_status()
        return {
            **status,
            "account_configured": bool(self._account_id),
            "token_configured": bool(self._api_token),
        }

    def client(self) -> Any:
        status = cloudflare_sdk_status()
        if not status.get("available"):
            raise RuntimeError(str(status.get("status") or "sdk_missing"))
        module = importlib.import_module("cloudflare")
        client_factory = getattr(module, "Cloudflare", None)
        if not callable(client_factory):
            raise RuntimeError("sdk_invalid")
        kwargs: dict[str, str] = {}
        if self._api_token:
            kwargs["api_token"] = self._api_token
        return client_factory(**kwargs)

    def list_accounts(self, *, per_page: int = 50) -> list[dict[str, Any]]:
        return self._call(lambda client: _serialize_collection(client.accounts.list(per_page=per_page)))

    def get_account(self, account_id: str | None = None) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        return self._call(lambda client: _serialize_resource(client.accounts.get(account_id=account_id)))

    def verify_token(self) -> dict[str, Any]:
        return self._rest_result("GET", "/user/tokens/verify")

    def list_zones(self, *, per_page: int = 50) -> list[dict[str, Any]]:
        return self._call(lambda client: _serialize_collection(client.zones.list(per_page=per_page)))

    def list_pages_projects(self, *, account_id: str | None = None, per_page: int = 10) -> list[dict[str, Any]]:
        account_id = self._require_account_id(account_id)
        return self._call(
            lambda client: _serialize_collection(
                client.pages.projects.list(
                    account_id=account_id,
                    per_page=_bounded_pages_page_size(per_page),
                )
            )
        )

    def get_pages_project(self, project_name: str, *, account_id: str | None = None) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        return self._call(
            lambda client: _serialize_resource(
                client.pages.projects.get(project_name, account_id=account_id)
            )
        )

    def create_pages_project(
        self,
        *,
        name: str,
        production_branch: str = "main",
        account_id: str | None = None,
        **params: Any,
    ) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        return self._call(
            lambda client: _serialize_resource(
                client.pages.projects.create(
                    account_id=account_id,
                    name=name,
                    production_branch=production_branch,
                    **params,
                )
            )
        )

    def update_pages_project(
        self,
        project_name: str,
        *,
        account_id: str | None = None,
        **params: Any,
    ) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        return self._call(
            lambda client: _serialize_resource(
                client.pages.projects.edit(project_name, account_id=account_id, **params)
            )
        )

    def delete_pages_project(self, project_name: str, *, account_id: str | None = None) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        return self._call(
            lambda client: _serialize_resource(
                client.pages.projects.delete(project_name, account_id=account_id)
            )
        )

    def create_pages_deployment(
        self,
        project_name: str,
        *,
        account_id: str | None = None,
        **params: Any,
    ) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        return self._call(
            lambda client: _serialize_resource(
                client.pages.projects.deployments.create(project_name, account_id=account_id, **params)
            )
        )

    def list_pages_deployments(
        self,
        project_name: str,
        *,
        account_id: str | None = None,
        per_page: int = 10,
    ) -> list[dict[str, Any]]:
        account_id = self._require_account_id(account_id)
        return self._call(
            lambda client: _serialize_collection(
                client.pages.projects.deployments.list(
                    project_name,
                    account_id=account_id,
                    per_page=_bounded_pages_page_size(per_page),
                )
            )
        )

    def get_pages_deployment(
        self,
        project_name: str,
        deployment_id: str,
        *,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        return self._call(
            lambda client: _serialize_resource(
                client.pages.projects.deployments.get(
                    deployment_id,
                    account_id=account_id,
                    project_name=project_name,
                )
            )
        )

    def delete_pages_deployment(
        self,
        project_name: str,
        deployment_id: str,
        *,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        return self._call(
            lambda client: _serialize_resource(
                client.pages.projects.deployments.delete(
                    deployment_id,
                    account_id=account_id,
                    project_name=project_name,
                )
            )
        )

    def list_workers(self, *, account_id: str | None = None, per_page: int = 50) -> list[dict[str, Any]]:
        account_id = self._require_account_id(account_id)
        sdk_result = self._try_sdk_path("workers.scripts.list", account_id=account_id, per_page=per_page)
        if sdk_result is not None:
            return _serialize_collection(sdk_result)
        return _serialize_collection(
            self._rest_result("GET", f"/accounts/{account_id}/workers/scripts", params={"per_page": per_page})
        )

    def get_worker(self, script_name: str, *, account_id: str | None = None) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        sdk_result = self._try_sdk_path("workers.scripts.get", script_name, account_id=account_id)
        if sdk_result is not None:
            return _serialize_resource(sdk_result)
        return self._rest_result("GET", f"/accounts/{account_id}/workers/scripts/{_quote_path(script_name)}")

    def upload_worker_module(
        self,
        script_name: str,
        *,
        main_module: str,
        modules: list[dict[str, Any]] | None = None,
        bindings: list[dict[str, Any]] | None = None,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        payload = {"main_module": main_module, "modules": list(modules or []), "bindings": list(bindings or [])}
        sdk_result = self._try_sdk_path(
            "workers.scripts.update",
            script_name,
            account_id=account_id,
            **payload,
        )
        if sdk_result is not None:
            return _serialize_resource(sdk_result)
        return self._rest_result("PUT", f"/accounts/{account_id}/workers/scripts/{_quote_path(script_name)}", payload)

    def patch_worker_settings(
        self,
        script_name: str,
        *,
        settings: Mapping[str, Any],
        account_id: str | None = None,
    ) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        sdk_result = self._try_sdk_path(
            "workers.scripts.settings.edit",
            script_name,
            account_id=account_id,
            **dict(settings),
        )
        if sdk_result is not None:
            return _serialize_resource(sdk_result)
        return self._rest_result(
            "PATCH",
            f"/accounts/{account_id}/workers/scripts/{_quote_path(script_name)}/settings",
            dict(settings),
        )

    def list_worker_deployments(
        self,
        script_name: str,
        *,
        account_id: str | None = None,
        per_page: int = 50,
    ) -> list[dict[str, Any]]:
        account_id = self._require_account_id(account_id)
        sdk_result = self._try_sdk_path(
            "workers.scripts.deployments.list",
            script_name,
            account_id=account_id,
            per_page=per_page,
        )
        if sdk_result is not None:
            return _serialize_collection(sdk_result)
        return _serialize_collection(
            self._rest_result(
                "GET",
                f"/accounts/{account_id}/workers/scripts/{_quote_path(script_name)}/deployments",
                params={"per_page": per_page},
            )
        )

    def create_worker_deployment(
        self,
        script_name: str,
        *,
        version_id: str | None = None,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        payload = {"version_id": version_id} if version_id else {}
        sdk_result = self._try_sdk_path(
            "workers.scripts.deployments.create",
            script_name,
            account_id=account_id,
            **payload,
        )
        if sdk_result is not None:
            return _serialize_resource(sdk_result)
        return self._rest_result(
            "POST",
            f"/accounts/{account_id}/workers/scripts/{_quote_path(script_name)}/deployments",
            payload,
        )

    def delete_worker(self, script_name: str, *, account_id: str | None = None) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        sdk_result = self._try_sdk_path("workers.scripts.delete", script_name, account_id=account_id)
        if sdk_result is not None:
            return _serialize_resource(sdk_result)
        return self._rest_result("DELETE", f"/accounts/{account_id}/workers/scripts/{_quote_path(script_name)}")

    def put_worker_secret(self, script_name: str, name: str, value: str, *, account_id: str | None = None) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        payload = {"name": name, "text": value, "type": "secret_text"}
        sdk_result = self._try_sdk_path("workers.scripts.secrets.update", script_name, account_id=account_id, **payload)
        if sdk_result is not None:
            return _serialize_resource(sdk_result)
        return self._rest_result(
            "PUT",
            f"/accounts/{account_id}/workers/scripts/{_quote_path(script_name)}/secrets",
            payload,
        )

    def patch_worker_secrets(
        self,
        script_name: str,
        secrets: Mapping[str, str],
        *,
        account_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return [
            self.put_worker_secret(script_name, str(name), str(value), account_id=account_id)
            for name, value in secrets.items()
            if str(name).strip()
        ]

    def list_d1_databases(self, *, account_id: str | None = None, per_page: int = 50) -> list[dict[str, Any]]:
        account_id = self._require_account_id(account_id)
        sdk_result = self._try_sdk_path("d1.database.list", account_id=account_id, per_page=per_page)
        if sdk_result is not None:
            return _serialize_collection(sdk_result)
        return _serialize_collection(
            self._rest_result("GET", f"/accounts/{account_id}/d1/database", params={"per_page": per_page})
        )

    def create_d1_database(self, name: str, *, account_id: str | None = None) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        sdk_result = self._try_sdk_path("d1.database.create", account_id=account_id, name=name)
        if sdk_result is not None:
            return _serialize_resource(sdk_result)
        return self._rest_result("POST", f"/accounts/{account_id}/d1/database", {"name": name})

    def get_d1_database(self, database_id: str, *, account_id: str | None = None) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        sdk_result = self._try_sdk_path("d1.database.get", database_id, account_id=account_id)
        if sdk_result is not None:
            return _serialize_resource(sdk_result)
        return self._rest_result("GET", f"/accounts/{account_id}/d1/database/{_quote_path(database_id)}")

    def delete_d1_database(self, database_id: str, *, account_id: str | None = None) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        sdk_result = self._try_sdk_path("d1.database.delete", database_id, account_id=account_id)
        if sdk_result is not None:
            return _serialize_resource(sdk_result)
        return self._rest_result("DELETE", f"/accounts/{account_id}/d1/database/{_quote_path(database_id)}")

    def query_d1_database(
        self,
        database_id: str,
        sql: str,
        params: list[Any] | None = None,
        *,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        payload = {"sql": sql, "params": list(params or [])}
        sdk_result = self._try_sdk_path("d1.database.query", database_id, account_id=account_id, **payload)
        if sdk_result is not None:
            return _serialize_resource(sdk_result)
        return self._rest_result("POST", f"/accounts/{account_id}/d1/database/{_quote_path(database_id)}/query", payload)

    def list_r2_buckets(self, *, account_id: str | None = None, per_page: int = 50) -> list[dict[str, Any]]:
        account_id = self._require_account_id(account_id)
        sdk_result = self._try_sdk_path("r2.buckets.list", account_id=account_id, per_page=per_page)
        if sdk_result is not None:
            return _serialize_collection(sdk_result)
        return _serialize_collection(self._rest_result("GET", f"/accounts/{account_id}/r2/buckets", params={"per_page": per_page}))

    def create_r2_bucket(self, name: str, *, account_id: str | None = None, location: str | None = None) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        payload = {"name": name, **({"location": location} if location else {})}
        sdk_result = self._try_sdk_path("r2.buckets.create", account_id=account_id, **payload)
        if sdk_result is not None:
            return _serialize_resource(sdk_result)
        return self._rest_result("POST", f"/accounts/{account_id}/r2/buckets", payload)

    def get_r2_bucket(self, name: str, *, account_id: str | None = None) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        sdk_result = self._try_sdk_path("r2.buckets.get", name, account_id=account_id)
        if sdk_result is not None:
            return _serialize_resource(sdk_result)
        return self._rest_result("GET", f"/accounts/{account_id}/r2/buckets/{_quote_path(name)}")

    def delete_r2_bucket(self, name: str, *, account_id: str | None = None) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        sdk_result = self._try_sdk_path("r2.buckets.delete", name, account_id=account_id)
        if sdk_result is not None:
            return _serialize_resource(sdk_result)
        return self._rest_result("DELETE", f"/accounts/{account_id}/r2/buckets/{_quote_path(name)}")

    def upload_r2_object(
        self,
        bucket_name: str,
        key: str,
        value: bytes | str,
        *,
        account_id: str | None = None,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        sdk_result = self._try_sdk_path(
            "r2.buckets.objects.update",
            bucket_name,
            key,
            account_id=account_id,
            value=value,
            content_type=content_type,
        )
        if sdk_result is not None:
            return _serialize_resource(sdk_result)
        headers = {"Content-Type": content_type or "application/octet-stream"}
        return self._rest_result(
            "PUT",
            f"/accounts/{account_id}/r2/buckets/{_quote_path(bucket_name)}/objects/{_quote_path(key)}",
            value,
            headers=headers,
        )

    def list_queues(self, *, account_id: str | None = None, per_page: int = 50) -> list[dict[str, Any]]:
        account_id = self._require_account_id(account_id)
        sdk_result = self._try_sdk_path("queues.list", account_id=account_id, per_page=per_page)
        if sdk_result is not None:
            return _serialize_collection(sdk_result)
        return _serialize_collection(self._rest_result("GET", f"/accounts/{account_id}/queues", params={"per_page": per_page}))

    def create_queue(self, name: str, *, account_id: str | None = None, **params: Any) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        payload = {"queue_name": name, **params}
        sdk_result = self._try_sdk_path("queues.create", account_id=account_id, **payload)
        if sdk_result is not None:
            return _serialize_resource(sdk_result)
        return self._rest_result("POST", f"/accounts/{account_id}/queues", payload)

    def get_queue(self, queue_id_or_name: str, *, account_id: str | None = None) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        sdk_result = self._try_sdk_path("queues.get", queue_id_or_name, account_id=account_id)
        if sdk_result is not None:
            return _serialize_resource(sdk_result)
        return self._rest_result("GET", f"/accounts/{account_id}/queues/{_quote_path(queue_id_or_name)}")

    def delete_queue(self, queue_id_or_name: str, *, account_id: str | None = None) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        sdk_result = self._try_sdk_path("queues.delete", queue_id_or_name, account_id=account_id)
        if sdk_result is not None:
            return _serialize_resource(sdk_result)
        return self._rest_result("DELETE", f"/accounts/{account_id}/queues/{_quote_path(queue_id_or_name)}")

    def create_queue_consumer(
        self,
        queue_id_or_name: str,
        *,
        script_name: str,
        account_id: str | None = None,
        **params: Any,
    ) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        payload = {"script_name": script_name, **params}
        sdk_result = self._try_sdk_path("queues.consumers.create", queue_id_or_name, account_id=account_id, **payload)
        if sdk_result is not None:
            return _serialize_resource(sdk_result)
        return self._rest_result(
            "POST",
            f"/accounts/{account_id}/queues/{_quote_path(queue_id_or_name)}/consumers",
            payload,
        )

    def list_workflows(self, *, account_id: str | None = None, per_page: int = 50) -> list[dict[str, Any]]:
        account_id = self._require_account_id(account_id)
        sdk_result = self._try_sdk_path("workflows.list", account_id=account_id, per_page=per_page)
        if sdk_result is not None:
            return _serialize_collection(sdk_result)
        return _serialize_collection(self._rest_result("GET", f"/accounts/{account_id}/workflows", params={"per_page": per_page}))

    def get_workflow(self, workflow_name: str, *, account_id: str | None = None) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        sdk_result = self._try_sdk_path("workflows.get", workflow_name, account_id=account_id)
        if sdk_result is not None:
            return _serialize_resource(sdk_result)
        return self._rest_result("GET", f"/accounts/{account_id}/workflows/{_quote_path(workflow_name)}")

    def put_workflow(
        self,
        workflow_name: str,
        *,
        script_name: str,
        class_name: str,
        bindings: list[dict[str, Any]] | None = None,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        payload = {"name": workflow_name, "script_name": script_name, "class_name": class_name, "bindings": list(bindings or [])}
        sdk_result = self._try_sdk_path("workflows.update", workflow_name, account_id=account_id, **payload)
        if sdk_result is not None:
            return _serialize_resource(sdk_result)
        return self._rest_result("PUT", f"/accounts/{account_id}/workflows/{_quote_path(workflow_name)}", payload)

    def delete_workflow(self, workflow_name: str, *, account_id: str | None = None) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        sdk_result = self._try_sdk_path("workflows.delete", workflow_name, account_id=account_id)
        if sdk_result is not None:
            return _serialize_resource(sdk_result)
        return self._rest_result("DELETE", f"/accounts/{account_id}/workflows/{_quote_path(workflow_name)}")

    def create_workflow_instance(self, workflow_name: str, payload: Mapping[str, Any], *, account_id: str | None = None) -> dict[str, Any]:
        account_id = self._require_account_id(account_id)
        body = {"params": dict(payload)}
        sdk_result = self._try_sdk_path("workflows.instances.create", workflow_name, account_id=account_id, **body)
        if sdk_result is not None:
            return _serialize_resource(sdk_result)
        return self._rest_result("POST", f"/accounts/{account_id}/workflows/{_quote_path(workflow_name)}/instances", body)

    def _require_account_id(self, account_id: str | None) -> str:
        resolved = str(account_id or self._account_id or "").strip()
        if not resolved:
            raise ValueError("cloudflare account_id is required")
        return resolved

    def _call(self, operation: Callable[[Any], Any]) -> Any:
        try:
            return operation(self.client())
        except Exception as exc:
            raise CloudflareSDKOperationError(
                _scrub_secret(str(exc), self._api_token),
                error_type=exc.__class__.__name__,
                status_code=getattr(exc, "status_code", None),
            ) from None

    def _try_sdk_path(self, dotted_path: str, *args: Any, **kwargs: Any) -> Any | None:
        if not cloudflare_sdk_status().get("available"):
            return None

        def operation(client: Any) -> Any:
            target = client
            for part in dotted_path.split("."):
                target = getattr(target, part, None)
                if target is None:
                    return None
            if not callable(target):
                return None
            return target(*args, **kwargs)

        return self._call(operation)

    def _rest_result(
        self,
        method: str,
        path: str,
        payload: Any | None = None,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        try:
            return _unwrap_cloudflare_result(
                self._rest_request(method, path, payload, params=params, headers=headers)
            )
        except CloudflareSDKOperationError as exc:
            raise CloudflareSDKOperationError(
                _scrub_secret(str(exc), self._api_token),
                error_type=exc.error_type,
                status_code=exc.status_code,
            ) from None
        except Exception as exc:
            raise CloudflareSDKOperationError(
                _scrub_secret(str(exc), self._api_token),
                error_type=exc.__class__.__name__,
                status_code=getattr(exc, "status_code", None),
            ) from None

    def _rest_request(
        self,
        method: str,
        path: str,
        payload: Any | None = None,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        if not self._api_token:
            raise CloudflareSDKOperationError("cloudflare api token is required", error_type="missing_token")
        query = urllib.parse.urlencode({str(key): value for key, value in dict(params or {}).items() if value is not None})
        url = f"{_CLOUDFLARE_API_BASE_URL}{path}"
        if query:
            url = f"{url}?{query}"
        request_headers = {
            "Authorization": f"Bearer {self._api_token}",
            "Accept": "application/json",
            **dict(headers or {}),
        }
        data: bytes | None = None
        if payload is not None:
            if isinstance(payload, bytes):
                data = payload
            elif isinstance(payload, str):
                data = payload.encode("utf-8")
            else:
                data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
                request_headers.setdefault("Content-Type", "application/json")
        request = urllib.request.Request(url, data=data, headers=request_headers, method=method.upper())
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raw_error = exc.read().decode("utf-8", errors="replace")
            raise CloudflareSDKOperationError(
                _scrub_secret(raw_error or str(exc), self._api_token),
                error_type="HTTPError",
                status_code=exc.code,
            ) from None
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"result": raw, "success": True}


def _serialize_collection(value: Iterable[Any], *, max_items: int = 100) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        for key in ("result", "items", "data"):
            nested = value.get(key)
            if isinstance(nested, Iterable) and not isinstance(nested, (str, bytes, Mapping)):
                value = nested
                break
    items: list[dict[str, Any]] = []
    for item in value:
        items.append(_serialize_resource(item))
        if len(items) >= max_items:
            break
    return items


def _bounded_pages_page_size(per_page: int) -> int:
    # Pages list endpoints reject larger page sizes even though the SDK accepts them.
    return max(1, min(int(per_page), _CLOUDFLARE_PAGES_MAX_PAGE_SIZE))


def _serialize_resource(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): _serialize_value(item) for key, item in value.items()}
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="json", exclude_none=True)
        if isinstance(dumped, Mapping):
            return {str(key): _serialize_value(item) for key, item in dumped.items()}
    if value is None:
        return {}
    return {"value": _serialize_value(value)}


def _serialize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _serialize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _serialize_resource(value)
    return value


def _scrub_secret(message: str, secret: str) -> str:
    if not secret:
        return message
    return message.replace(secret, "[redacted]")


def _unwrap_cloudflare_result(payload: Any) -> Any:
    if not isinstance(payload, Mapping):
        return payload
    if payload.get("success") is False:
        message = str(payload.get("errors") or payload.get("messages") or "Cloudflare API request failed")
        raise CloudflareSDKOperationError(message, error_type="cloudflare_api_error")
    if "result" in payload:
        return payload.get("result")
    return payload


def _quote_path(value: Any) -> str:
    return urllib.parse.quote(str(value or "").strip(), safe="")
