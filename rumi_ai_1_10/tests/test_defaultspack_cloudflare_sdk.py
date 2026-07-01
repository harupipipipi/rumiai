from __future__ import annotations

import sys
from types import SimpleNamespace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_cloudflare_sdk_adapter_reports_missing_sdk(monkeypatch):
    from core_runtime.cloudflare import sdk_client

    monkeypatch.setattr(sdk_client.importlib.util, "find_spec", lambda _name: None)

    status = sdk_client.cloudflare_sdk_status()
    adapter_status = sdk_client.CloudflareSDKAdapter(api_token="secret", account_id="acct").status()

    assert status["available"] is False
    assert status["status"] == "sdk_missing"
    assert adapter_status["status"] == "sdk_missing"
    assert adapter_status["token_configured"] is True
    assert adapter_status["account_configured"] is True


def test_cloudflare_oauth_status_includes_sdk_missing(monkeypatch):
    from core_runtime.cloudflare import sdk_client
    from domain.ai_client.oauth_store import provider_oauth_status

    monkeypatch.setattr(sdk_client.importlib.util, "find_spec", lambda _name: None)

    status = provider_oauth_status("cloudflare")

    assert status["cloudflare_sdk"]["status"] == "sdk_missing"
    assert status["provisioning"]["sdk_status"] == "sdk_missing"


def test_cloudflare_sdk_adapter_routes_pages_operations_through_sdk(monkeypatch):
    from core_runtime.cloudflare import sdk_client

    calls: list[tuple[str, dict[str, object]]] = []

    class Resource:
        def __init__(self, **payload: object) -> None:
            self._payload = payload

        def model_dump(self, *, mode: str = "json", exclude_none: bool = True) -> dict[str, object]:
            assert mode == "json"
            assert exclude_none is True
            return dict(self._payload)

    class Deployments:
        def create(self, project_name: str, **kwargs: object) -> Resource:
            calls.append(("pages.projects.deployments.create", {"project_name": project_name, **kwargs}))
            return Resource(id="deployment-id", project_name=project_name)

        def list(self, project_name: str, **kwargs: object) -> list[Resource]:
            calls.append(("pages.projects.deployments.list", {"project_name": project_name, **kwargs}))
            return [Resource(id="deployment-id", project_name=project_name)]

        def delete(self, deployment_id: str, **kwargs: object) -> dict[str, object]:
            calls.append(("pages.projects.deployments.delete", {"deployment_id": deployment_id, **kwargs}))
            return {"id": deployment_id, "deleted": True}

    class Projects:
        def __init__(self) -> None:
            self.deployments = Deployments()

        def create(self, **kwargs: object) -> Resource:
            calls.append(("pages.projects.create", dict(kwargs)))
            return Resource(name=str(kwargs["name"]), production_branch=str(kwargs["production_branch"]))

        def list(self, **kwargs: object) -> list[Resource]:
            calls.append(("pages.projects.list", dict(kwargs)))
            return [Resource(name="rumi-pr440-smoke-pages-test")]

        def edit(self, project_name: str, **kwargs: object) -> Resource:
            calls.append(("pages.projects.edit", {"project_name": project_name, **kwargs}))
            return Resource(name=project_name, updated=True)

        def delete(self, project_name: str, **kwargs: object) -> dict[str, object]:
            calls.append(("pages.projects.delete", {"project_name": project_name, **kwargs}))
            return {"name": project_name, "deleted": True}

    class Accounts:
        def list(self, **kwargs: object) -> list[Resource]:
            calls.append(("accounts.list", dict(kwargs)))
            return [Resource(id="account-id", name="Test Account")]

    class FakeCloudflare:
        def __init__(self, **kwargs: object) -> None:
            calls.append(("Cloudflare", dict(kwargs)))
            self.accounts = Accounts()
            self.pages = SimpleNamespace(projects=Projects())

    monkeypatch.setattr(sdk_client.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(sdk_client.importlib, "import_module", lambda _name: SimpleNamespace(Cloudflare=FakeCloudflare))

    adapter = sdk_client.CloudflareSDKAdapter(api_token="cloudflare-secret-token", account_id="account-id")
    accounts = adapter.list_accounts(per_page=1)
    project = adapter.create_pages_project(name="rumi-pr440-smoke-pages-test")
    projects = adapter.list_pages_projects(per_page=50)
    updated = adapter.update_pages_project("rumi-pr440-smoke-pages-test", production_branch="main")
    deployment = adapter.create_pages_deployment("rumi-pr440-smoke-pages-test", branch="main")
    deployments = adapter.list_pages_deployments("rumi-pr440-smoke-pages-test", per_page=50)
    deleted_deployment = adapter.delete_pages_deployment("rumi-pr440-smoke-pages-test", "deployment-id")
    deleted_project = adapter.delete_pages_project("rumi-pr440-smoke-pages-test")

    assert accounts == [{"id": "account-id", "name": "Test Account"}]
    assert project["name"] == "rumi-pr440-smoke-pages-test"
    assert projects == [{"name": "rumi-pr440-smoke-pages-test"}]
    assert updated["updated"] is True
    assert deployment["id"] == "deployment-id"
    assert deployments == [{"id": "deployment-id", "project_name": "rumi-pr440-smoke-pages-test"}]
    assert deleted_deployment["deleted"] is True
    assert deleted_project["deleted"] is True
    assert [name for name, _payload in calls] == [
        "Cloudflare",
        "accounts.list",
        "Cloudflare",
        "pages.projects.create",
        "Cloudflare",
        "pages.projects.list",
        "Cloudflare",
        "pages.projects.edit",
        "Cloudflare",
        "pages.projects.deployments.create",
        "Cloudflare",
        "pages.projects.deployments.list",
        "Cloudflare",
        "pages.projects.deployments.delete",
        "Cloudflare",
        "pages.projects.delete",
    ]
    assert calls[0][1] == {"api_token": "cloudflare-secret-token"}
    assert calls[5][1]["per_page"] == 10
    assert calls[11][1]["per_page"] == 10
    assert "cloudflare-secret-token" not in str(
        [accounts, project, projects, updated, deployment, deployments, deleted_deployment, deleted_project]
    )


def test_cloudflare_sdk_adapter_redacts_token_from_errors(monkeypatch):
    from core_runtime.cloudflare import sdk_client

    class Projects:
        def list(self, **_kwargs: object) -> list[object]:
            raise RuntimeError("permission denied for cloudflare-secret-token")

    class FakeCloudflare:
        def __init__(self, **_kwargs: object) -> None:
            self.pages = SimpleNamespace(projects=Projects())

    monkeypatch.setattr(sdk_client.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(sdk_client.importlib, "import_module", lambda _name: SimpleNamespace(Cloudflare=FakeCloudflare))

    adapter = sdk_client.CloudflareSDKAdapter(api_token="cloudflare-secret-token", account_id="account-id")
    try:
        adapter.list_pages_projects()
    except sdk_client.CloudflareSDKOperationError as exc:
        error = exc.to_dict()
    else:
        raise AssertionError("Cloudflare SDK errors should be wrapped")

    assert "cloudflare-secret-token" not in str(error)
    assert error["message"] == "permission denied for [redacted]"
