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
    assert status["cloudflare_environment"]["schema"] == "rumi.cloudflare.environment.v1"
    assert status["cloudflare_environment"]["status"] == "needs_check"
    assert status["provisioning"]["runner_deploy_ready"] is False
    assert status["provisioning"]["constraints"]["cloudflare_sandbox_requires_workers_paid"] is True
    assert status["provisioning"]["constraints"]["all_tools_cloudflare_native_supported"] is False
    assert status["provisioning"]["constraints"]["pc_local_tools_require_pc_bridge"] is True
    assert status["provisioning"]["constraints"]["pc_local_browser_computer_files_terminal_not_cloudflare_native"] is True
    assert status["provisioning"]["constraints"]["pc_tool_bridge_requires_named_tunnel"] is True


def test_cloudflare_oauth_status_can_run_active_diagnostics(monkeypatch):
    from core_runtime.cloudflare import diagnostics, sdk_client
    from domain.ai_client.oauth_store import provider_oauth_status

    calls: list[bool] = []

    monkeypatch.setattr(sdk_client.importlib.util, "find_spec", lambda _name: None)

    def fake_environment_status(*, active=False, command_runner=None, api_fetcher=None, api_token=None, env=None):
        del command_runner, api_fetcher, api_token, env
        calls.append(bool(active))
        return {
            "schema": "rumi.cloudflare.environment.v1",
            "active": bool(active),
            "status": "blocked" if active else "needs_check",
            "runner_deploy_ready": False,
            "sandbox_ready": False,
            "pages_ready": False,
            "zones_ready": False,
            "named_tunnel_ready": False,
            "stable_pc_tunnel_ready": False,
            "pc_tool_bridge_ready": False,
            "blockers": [{"code": "CLOUDFLARE_ACTIVE_TEST", "message": "active diagnostics ran"}] if active else [],
            "constraints": {"cloudflare_sandbox_requires_workers_paid": True},
        }

    monkeypatch.setattr(diagnostics, "cloudflare_environment_status", fake_environment_status)

    status = provider_oauth_status("cloudflare", active_diagnostics=True)

    assert calls == [True]
    assert status["cloudflare_environment"]["active"] is True
    assert status["provisioning"]["blockers"] == [
        {"code": "CLOUDFLARE_ACTIVE_TEST", "message": "active diagnostics ran"}
    ]


def test_cloudflare_oauth_active_diagnostics_passes_imported_token_without_leaking_it(monkeypatch):
    from core_runtime.cloudflare import diagnostics, sdk_client
    from domain.ai_client import oauth_store

    captured: dict[str, object] = {}

    monkeypatch.setattr(sdk_client.importlib.util, "find_spec", lambda _name: None)
    monkeypatch.setattr(oauth_store, "get_provider_access_token", lambda provider_id, *, pack_root=None: "cloudflare-secret-token")

    def fake_environment_status(*, active=False, command_runner=None, api_fetcher=None, api_token=None, env=None):
        del command_runner, api_fetcher, env
        captured["active"] = active
        captured["api_token"] = api_token
        return {
            "schema": "rumi.cloudflare.environment.v1",
            "active": bool(active),
            "status": "blocked",
            "runner_deploy_ready": False,
            "sandbox_ready": False,
            "pages_ready": False,
            "zones_ready": False,
            "named_tunnel_ready": False,
            "stable_pc_tunnel_ready": False,
            "pc_tool_bridge_ready": False,
            "blockers": [],
            "constraints": {},
        }

    monkeypatch.setattr(diagnostics, "cloudflare_environment_status", fake_environment_status)

    status = oauth_store.provider_oauth_status("cloudflare", active_diagnostics=True)

    assert captured == {"active": True, "api_token": "cloudflare-secret-token"}
    assert "cloudflare-secret-token" not in str(status)


def test_cloudflare_oauth_block_active_diagnostics_action(monkeypatch):
    from blocks.ai import oauth as oauth_block

    captured: dict[str, object] = {}

    def fake_status(provider_id: str, *, active_diagnostics: bool = False):
        captured["provider_id"] = provider_id
        captured["active_diagnostics"] = active_diagnostics
        return {"provider_id": provider_id, "cloudflare_environment": {"active": active_diagnostics}}

    monkeypatch.setattr(oauth_block, "provider_oauth_status", fake_status)

    result = oauth_block.run(
        {"_method": "POST", "provider_id": "cloudflare", "action": "active_diagnostics"},
        {},
    )

    assert captured == {"provider_id": "cloudflare", "active_diagnostics": True}
    assert result["status"] == "ok"
    assert result["data"]["provider"]["cloudflare_environment"]["active"] is True


def test_cloudflare_environment_active_diagnostics_reports_paid_plan_and_pc_bridge_constraints(monkeypatch):
    from core_runtime.cloudflare import diagnostics

    monkeypatch.setattr(
        diagnostics.shutil,
        "which",
        lambda name: f"/usr/local/bin/{name}" if name in {"cloudflared", "docker"} else None,
    )

    def runner(argv, _timeout):
        args = tuple(argv)
        if args == ("/usr/local/bin/npx", "wrangler", "--version"):
            return diagnostics.CommandResult(0, "4.106.0\n", "")
        if args == ("/usr/local/bin/npx", "wrangler", "whoami"):
            return diagnostics.CommandResult(0, "You are logged in with an OAuth Token.\n", "")
        if args == ("/usr/local/bin/npx", "wrangler", "pages", "project", "list"):
            return diagnostics.CommandResult(0, "rumi-pages\n", "")
        if args == ("/usr/local/bin/npx", "wrangler", "containers", "list"):
            return diagnostics.CommandResult(
                1,
                "",
                "Unauthorized: Deploying containers requires the Workers Paid plan.",
            )
        if args == ("/usr/local/bin/npx", "wrangler", "tunnel", "list"):
            return diagnostics.CommandResult(0, "", "")
        if args == ("/usr/local/bin/cloudflared", "--version"):
            return diagnostics.CommandResult(0, "cloudflared version 2026.3.0\n", "")
        if args == ("/usr/local/bin/cloudflared", "tunnel", "list"):
            return diagnostics.CommandResult(1, "", "No file cert.pem; client didn't specify origincert path")
        if args == ("/usr/local/bin/docker", "info", "--format", "{{json .ServerVersion}}"):
            return diagnostics.CommandResult(1, "", "Cannot connect to the Docker daemon")
        return diagnostics.CommandResult(127, "", f"unexpected command: {args}")

    status = diagnostics.cloudflare_environment_status(
        active=True,
        command_runner=runner,
        env={"RUMI_WRANGLER_COMMAND": "/usr/local/bin/npx wrangler"},
    )

    assert status["status"] == "blocked"
    assert status["pages_ready"] is True
    assert status["runner_deploy_ready"] is False
    assert status["free_plan_supported"] is False
    assert status["checks"]["containers"]["status"] == "paid_plan_required"
    assert status["checks"]["zones"]["status"] == "not_checked"
    assert status["checks"]["pc_tunnel_env"]["status"] == "not_configured"
    assert status["checks"]["pc_tool_bridge_env"]["status"] == "not_configured"
    assert status["constraints"]["cloudflare_sandbox_requires_workers_paid"] is True
    assert status["constraints"]["all_tools_cloudflare_native_supported"] is False
    assert status["constraints"]["pc_local_tools_require_pc_bridge"] is True
    assert status["constraints"]["pc_local_browser_computer_files_terminal_not_cloudflare_native"] is True
    assert "browser/computer/files/terminal tools are not Cloudflare-native" in status["deployment"]["pc_local_tools_note"]


def test_cloudflare_environment_redacts_api_token_from_zone_errors(monkeypatch):
    from core_runtime.cloudflare import diagnostics

    monkeypatch.setattr(diagnostics.shutil, "which", lambda _name: None)

    def fetcher(_path, token, _timeout):
        raise RuntimeError(f"permission denied for {token}")

    status = diagnostics.cloudflare_environment_status(
        active=True,
        command_runner=lambda _argv, _timeout: diagnostics.CommandResult(127, "", "missing"),
        api_fetcher=fetcher,
        api_token="cloudflare-secret-token",
        env={},
    )

    assert status["checks"]["zones"]["status"] == "unavailable"
    assert "cloudflare-secret-token" not in str(status)
    assert "[redacted]" in status["checks"]["zones"]["detail"]


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

    class Zones:
        def list(self, **kwargs: object) -> list[Resource]:
            calls.append(("zones.list", dict(kwargs)))
            return [Resource(id="zone-id", name="example.com")]

    class FakeCloudflare:
        def __init__(self, **kwargs: object) -> None:
            calls.append(("Cloudflare", dict(kwargs)))
            self.accounts = Accounts()
            self.zones = Zones()
            self.pages = SimpleNamespace(projects=Projects())

    monkeypatch.setattr(sdk_client.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(sdk_client.importlib, "import_module", lambda _name: SimpleNamespace(Cloudflare=FakeCloudflare))

    adapter = sdk_client.CloudflareSDKAdapter(api_token="cloudflare-secret-token", account_id="account-id")
    accounts = adapter.list_accounts(per_page=1)
    zones = adapter.list_zones(per_page=50)
    project = adapter.create_pages_project(name="rumi-pr440-smoke-pages-test")
    projects = adapter.list_pages_projects(per_page=50)
    updated = adapter.update_pages_project("rumi-pr440-smoke-pages-test", production_branch="main")
    deployment = adapter.create_pages_deployment("rumi-pr440-smoke-pages-test", branch="main")
    deployments = adapter.list_pages_deployments("rumi-pr440-smoke-pages-test", per_page=50)
    deleted_deployment = adapter.delete_pages_deployment("rumi-pr440-smoke-pages-test", "deployment-id")
    deleted_project = adapter.delete_pages_project("rumi-pr440-smoke-pages-test")

    assert accounts == [{"id": "account-id", "name": "Test Account"}]
    assert zones == [{"id": "zone-id", "name": "example.com"}]
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
        "zones.list",
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
    assert calls[3][1]["per_page"] == 50
    assert calls[7][1]["per_page"] == 10
    assert calls[13][1]["per_page"] == 10
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


def test_cloudflare_sdk_adapter_routes_runner_resources_through_rest_fallback(monkeypatch):
    from core_runtime.cloudflare import sdk_client

    calls: list[tuple[str, str, object, dict[str, object]]] = []

    monkeypatch.setattr(sdk_client.importlib.util, "find_spec", lambda _name: None)

    def fake_rest(self, method, path, payload=None, *, params=None, headers=None):
        del headers
        calls.append((method, path, payload, dict(params or {})))
        if path.endswith("/d1/database") and method == "GET":
            return {"success": True, "result": [{"uuid": "d1-id", "name": "rumi-state"}]}
        if path.endswith("/d1/database") and method == "POST":
            return {"success": True, "result": {"uuid": "d1-new", "name": payload["name"]}}
        if path.endswith("/r2/buckets") and method == "GET":
            return {"success": True, "result": [{"name": "rumi-artifacts"}]}
        if path.endswith("/queues") and method == "POST":
            return {"success": True, "result": {"id": "queue-id", "queue_name": payload["queue_name"]}}
        if "/workers/scripts/rumi-runner/secrets" in path:
            assert payload["text"] == "runner-secret"
            return {"success": True, "result": {"name": payload["name"]}}
        if path.endswith("/workflows/rumi-workflow/instances"):
            return {"success": True, "result": {"id": "instance-id"}}
        return {"success": True, "result": {"ok": True}}

    monkeypatch.setattr(sdk_client.CloudflareSDKAdapter, "_rest_request", fake_rest)

    adapter = sdk_client.CloudflareSDKAdapter(api_token="cloudflare-secret-token", account_id="account-id")
    d1 = adapter.list_d1_databases()
    created_d1 = adapter.create_d1_database("rumi-state")
    r2 = adapter.list_r2_buckets()
    queue = adapter.create_queue("rumi-tasks")
    secret = adapter.put_worker_secret("rumi-runner", "RUMI_CALLBACK_TOKEN", "runner-secret")
    instance = adapter.create_workflow_instance("rumi-workflow", {"job": "smoke"})

    assert d1 == [{"uuid": "d1-id", "name": "rumi-state"}]
    assert created_d1["uuid"] == "d1-new"
    assert r2 == [{"name": "rumi-artifacts"}]
    assert queue["queue_name"] == "rumi-tasks"
    assert secret["name"] == "RUMI_CALLBACK_TOKEN"
    assert instance["id"] == "instance-id"
    assert [call[0:2] for call in calls] == [
        ("GET", "/accounts/account-id/d1/database"),
        ("POST", "/accounts/account-id/d1/database"),
        ("GET", "/accounts/account-id/r2/buckets"),
        ("POST", "/accounts/account-id/queues"),
        ("PUT", "/accounts/account-id/workers/scripts/rumi-runner/secrets"),
        ("POST", "/accounts/account-id/workflows/rumi-workflow/instances"),
    ]
    assert "cloudflare-secret-token" not in str([d1, created_d1, r2, queue, secret, instance])


def test_cloudflare_sdk_rest_errors_are_redacted(monkeypatch):
    from core_runtime.cloudflare import sdk_client

    monkeypatch.setattr(sdk_client.importlib.util, "find_spec", lambda _name: None)

    def fake_rest(self, *_args, **_kwargs):
        raise RuntimeError("token cloudflare-secret-token denied")

    monkeypatch.setattr(sdk_client.CloudflareSDKAdapter, "_rest_request", fake_rest)

    adapter = sdk_client.CloudflareSDKAdapter(api_token="cloudflare-secret-token", account_id="account-id")
    try:
        adapter.list_workers()
    except sdk_client.CloudflareSDKOperationError as exc:
        payload = exc.to_dict()
    else:
        raise AssertionError("Cloudflare REST errors should be wrapped")

    assert "cloudflare-secret-token" not in str(payload)
    assert payload["message"] == "token [redacted] denied"
