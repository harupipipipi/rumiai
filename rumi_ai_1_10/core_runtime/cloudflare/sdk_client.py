from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
import importlib
import importlib.util
from typing import Any


_CLOUDFLARE_PAGES_MAX_PAGE_SIZE = 10


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


def _serialize_collection(value: Iterable[Any], *, max_items: int = 100) -> list[dict[str, Any]]:
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
