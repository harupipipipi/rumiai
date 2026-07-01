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
    assert status["provisioning"]["constraints"]["pc_tool_bridge_requires_named_tunnel"] is True
    assert status["provisioning"]["constraints"]["stable_pc_tunnel_requires_cloudflare_managed_zone"] is True
    assert status["provisioning"]["constraints"]["pages_projects_do_not_create_cloudflare_dns_zones"] is True
    assert (
        status["provisioning"]["environment"]["deployment"]["sandbox_bridge_scaffold"]
        == "rumi_ai_1_10/ecosystem/defaultspack/cloudflare/sandbox_bridge"
    )
    assert (
        status["provisioning"]["environment"]["deployment"]["pc_tool_bridge_scaffold"]
        == "rumi_ai_1_10/ecosystem/defaultspack/cloudflare/pc_tool_bridge"
    )


def test_cloudflare_oauth_status_can_run_active_diagnostics(monkeypatch):
    from core_runtime.cloudflare import diagnostics, sdk_client
    from domain.ai_client.oauth_store import provider_oauth_status

    calls: list[bool] = []

    monkeypatch.setattr(sdk_client.importlib.util, "find_spec", lambda _name: None)

    def fake_environment_status(*, active=False, command_runner=None, env=None):
        del command_runner, env
        calls.append(bool(active))
        return {
            "schema": "rumi.cloudflare.environment.v1",
            "active": bool(active),
            "status": "blocked" if active else "needs_check",
            "runner_deploy_ready": False,
            "sandbox_ready": False,
            "pages_ready": False,
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


def test_cloudflare_environment_prefers_local_wrangler_before_npx(monkeypatch):
    from core_runtime.cloudflare import diagnostics

    local_bin = "/repo/rumi_ai_1_10/ecosystem/defaultspack/cloudflare/pc_tool_bridge/node_modules/.bin/wrangler"

    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: "/usr/local/bin/npx" if name == "npx" else None)
    monkeypatch.setattr(
        diagnostics.os.path,
        "abspath",
        lambda path: "/repo/rumi_ai_1_10" if str(path).endswith("../..") else str(path),
    )
    monkeypatch.setattr(diagnostics.os.path, "isfile", lambda path: path == local_bin)
    monkeypatch.setattr(diagnostics.os, "access", lambda path, _mode: path == local_bin)

    assert diagnostics._wrangler_command({}) == [local_bin]


def test_cloudflare_environment_uses_noninteractive_npx_wrangler(monkeypatch):
    from core_runtime.cloudflare import diagnostics

    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: "/usr/local/bin/npx" if name == "npx" else None)
    monkeypatch.setattr(diagnostics.os.path, "isfile", lambda _path: False)

    assert diagnostics._wrangler_command({}) == ["/usr/local/bin/npx", "--yes", "wrangler"]


def test_cloudflare_environment_active_diagnostics_reports_paid_plan_and_tunnel_blockers(monkeypatch):
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
            return diagnostics.CommandResult(0, "rumi-line-webhook-relay\n", "")
        if args == ("/usr/local/bin/npx", "wrangler", "containers", "list"):
            return diagnostics.CommandResult(
                1,
                "",
                "Unauthorized: You do not have access to Cloudflare Containers. Deploying containers requires the Workers Paid plan.",
            )
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
    assert status["sandbox_ready"] is False
    assert status["runner_deploy_ready"] is False
    assert status["named_tunnel_ready"] is False
    assert status["stable_pc_tunnel_ready"] is False
    assert status["pc_tool_bridge_ready"] is False
    assert status["free_plan_supported"] is False
    assert status["checks"]["containers"]["status"] == "paid_plan_required"
    assert status["checks"]["named_tunnel"]["status"] == "origin_cert_missing"
    assert status["checks"]["pc_tunnel_env"]["status"] == "not_configured"
    assert status["checks"]["pc_tool_bridge_env"]["status"] == "not_configured"
    assert status["checks"]["docker"]["status"] == "daemon_unavailable"
    assert status["deployment"]["sandbox_bridge_url_env"] == "RUMI_CLOUDFLARE_SANDBOX_BRIDGE_URL"
    assert status["deployment"]["pc_tunnel_scaffold"] == "rumi_ai_1_10/ecosystem/defaultspack/cloudflare/pc_tunnel"
    assert status["deployment"]["pc_tool_bridge_scaffold"] == "rumi_ai_1_10/ecosystem/defaultspack/cloudflare/pc_tool_bridge"
    assert status["constraints"]["quick_tunnels_do_not_support_sse"] is True
    assert status["constraints"]["trycloudflare_urls_are_not_stable_pc_tunnel_hostnames"] is True
    assert status["constraints"]["all_tools_cloudflare_native_supported"] is False
    assert status["constraints"]["pc_local_tools_require_pc_bridge"] is True
    assert status["constraints"]["pc_tool_bridge_does_not_upload_pc_local_tools"] is True
    assert status["constraints"]["pc_tool_bridge_preserves_pc_approval_authority"] is True
    assert {item["code"] for item in status["blockers"]} >= {
        "CLOUDFLARE_CONTAINERS_PAID_PLAN_REQUIRED",
        "CLOUDFLARE_NAMED_TUNNEL_ORIGIN_CERT_MISSING",
        "CLOUDFLARE_PC_TUNNEL_ENV_NOT_CONFIGURED",
        "CLOUDFLARE_PC_TOOL_BRIDGE_ENV_NOT_CONFIGURED",
        "CLOUDFLARE_DOCKER_DAEMON_UNAVAILABLE",
    }


def test_cloudflare_environment_accepts_wrangler_managed_named_tunnel(monkeypatch):
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
            return diagnostics.CommandResult(0, "rumi-line-webhook-relay\n", "")
        if args == ("/usr/local/bin/npx", "wrangler", "containers", "list"):
            return diagnostics.CommandResult(
                1,
                "",
                "Unauthorized: Deploying containers requires the Workers Paid plan.",
            )
        if args == ("/usr/local/bin/npx", "wrangler", "tunnel", "list"):
            return diagnostics.CommandResult(
                0,
                "09fe4401-091d-45b2-ba3a-126dcea4be0c rumi-pc inactive cfd_tunnel\n",
                "",
            )
        if args == ("/usr/local/bin/cloudflared", "--version"):
            return diagnostics.CommandResult(0, "cloudflared version 2026.3.0\n", "")
        if args == ("/usr/local/bin/docker", "info", "--format", "{{json .ServerVersion}}"):
            return diagnostics.CommandResult(0, '"29.1.3"\n', "")
        return diagnostics.CommandResult(127, "", f"unexpected command: {args}")

    status = diagnostics.cloudflare_environment_status(
        active=True,
        command_runner=runner,
        env={"RUMI_WRANGLER_COMMAND": "/usr/local/bin/npx wrangler"},
    )

    assert status["named_tunnel_ready"] is True
    assert status["stable_pc_tunnel_ready"] is False
    assert status["checks"]["named_tunnel"]["status"] == "ready"
    assert status["checks"]["named_tunnel"]["manager"] == "wrangler"
    assert status["checks"]["named_tunnel"]["tunnel_count"] == 1
    assert "CLOUDFLARE_NAMED_TUNNEL_ORIGIN_CERT_MISSING" not in {
        item["code"] for item in status["blockers"]
    }
    assert {item["code"] for item in status["blockers"]} >= {
        "CLOUDFLARE_CONTAINERS_PAID_PLAN_REQUIRED",
        "CLOUDFLARE_PC_TUNNEL_ENV_NOT_CONFIGURED",
        "CLOUDFLARE_PC_TOOL_BRIDGE_ENV_NOT_CONFIGURED",
    }


def test_cloudflare_environment_rejects_pages_dev_as_stable_pc_tunnel(monkeypatch):
    from core_runtime.cloudflare import diagnostics

    monkeypatch.setattr(diagnostics.shutil, "which", lambda _name: None)

    status = diagnostics.cloudflare_environment_status(
        active=True,
        command_runner=lambda _argv, _timeout: diagnostics.CommandResult(127, "", "missing"),
        env={
            "RUMI_CLOUDFLARE_PC_TUNNEL_HOSTNAME": "rumi.pages.dev",
            "RUMI_CLOUDFLARE_PC_TUNNEL_ORIGIN_URL": "http://127.0.0.1:8765",
        },
    )

    assert status["checks"]["pc_tunnel_env"]["status"] == "pages_dev_not_supported"
    assert status["checks"]["pc_tunnel_env"]["hostname"] == "rumi.pages.dev"
    assert status["constraints"]["pages_dev_is_not_a_pc_tunnel_hostname"] is True
    assert "CLOUDFLARE_PC_TUNNEL_ENV_PAGES_DEV_NOT_SUPPORTED" in {
        item["code"] for item in status["blockers"]
    }


def test_cloudflare_environment_rejects_quick_tunnel_and_private_hosts(monkeypatch):
    from core_runtime.cloudflare import diagnostics

    monkeypatch.setattr(diagnostics.shutil, "which", lambda _name: None)

    quick = diagnostics.cloudflare_environment_status(
        active=True,
        command_runner=lambda _argv, _timeout: diagnostics.CommandResult(127, "", "missing"),
        env={
            "RUMI_CLOUDFLARE_PC_TUNNEL_HOSTNAME": "random.trycloudflare.com",
            "RUMI_CLOUDFLARE_PC_TUNNEL_ORIGIN_URL": "http://127.0.0.1:8765",
        },
    )
    private = diagnostics.cloudflare_environment_status(
        active=True,
        command_runner=lambda _argv, _timeout: diagnostics.CommandResult(127, "", "missing"),
        env={
            "RUMI_CLOUDFLARE_PC_TUNNEL_HOSTNAME": "192.168.1.20",
            "RUMI_CLOUDFLARE_PC_TUNNEL_ORIGIN_URL": "http://127.0.0.1:8765",
        },
    )
    url = diagnostics.cloudflare_environment_status(
        active=True,
        command_runner=lambda _argv, _timeout: diagnostics.CommandResult(127, "", "missing"),
        env={
            "RUMI_CLOUDFLARE_PC_TUNNEL_HOSTNAME": "https://rumi-pc.example.com/path",
            "RUMI_CLOUDFLARE_PC_TUNNEL_ORIGIN_URL": "http://127.0.0.1:8765",
        },
    )

    assert quick["checks"]["pc_tunnel_env"]["status"] == "trycloudflare_not_stable"
    assert private["checks"]["pc_tunnel_env"]["status"] == "not_public_hostname"
    assert url["checks"]["pc_tunnel_env"]["status"] == "invalid_hostname"


def test_cloudflare_environment_accepts_configured_pc_tool_bridge_env(monkeypatch):
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
            return diagnostics.CommandResult(0, "container-id\n", "")
        if args == ("/usr/local/bin/npx", "wrangler", "tunnel", "list"):
            return diagnostics.CommandResult(
                0,
                "09fe4401-091d-45b2-ba3a-126dcea4be0c rumi-pc active cfd_tunnel\n",
                "",
            )
        if args == ("/usr/local/bin/cloudflared", "--version"):
            return diagnostics.CommandResult(0, "cloudflared version 2026.3.0\n", "")
        if args == ("/usr/local/bin/cloudflared", "tunnel", "list"):
            return diagnostics.CommandResult(0, "rumi-pc\n", "")
        if args == ("/usr/local/bin/docker", "info", "--format", "{{json .ServerVersion}}"):
            return diagnostics.CommandResult(0, '"29.0.0"\n', "")
        return diagnostics.CommandResult(127, "", f"unexpected command: {args}")

    status = diagnostics.cloudflare_environment_status(
        active=True,
        command_runner=runner,
        env={
            "RUMI_WRANGLER_COMMAND": "/usr/local/bin/npx wrangler",
            "RUMI_CLOUDFLARE_PC_TUNNEL_HOSTNAME": "rumi-pc.example.com",
            "RUMI_CLOUDFLARE_PC_TOOL_BRIDGE_URL": "https://rumi-cloudflare-pc-tool-bridge.example.workers.dev",
            "RUMI_PC_TOOL_BRIDGE_TOKEN": "client-secret",
            "RUMI_PC_RUNTIME_BEARER": "pc-runtime-secret",
            "RUMI_PC_ORIGIN": "https://rumi-pc.example.com",
            "RUMI_PC_TOOL_BRIDGE_ALLOWED_ORIGIN": "https://app.example.com",
        },
    )

    assert status["status"] == "ready"
    assert status["pc_tool_bridge_ready"] is True
    assert status["stable_pc_tunnel_ready"] is True
    assert status["checks"]["pc_tool_bridge_env"]["status"] == "configured"
    assert status["checks"]["pc_tool_bridge_env"]["bridge_token_configured"] is True
    assert status["checks"]["pc_tool_bridge_env"]["pc_runtime_bearer_configured"] is True
    assert status["checks"]["pc_tool_bridge_env"]["allowed_origin"] == "https://app.example.com"
    assert status["checks"]["pc_tool_bridge_env"]["pc_origin"] == "https://rumi-pc.example.com"
    assert status["blockers"] == []


def test_cloudflare_environment_rejects_invalid_pc_tool_bridge_env(monkeypatch):
    from core_runtime.cloudflare import diagnostics

    monkeypatch.setattr(diagnostics.shutil, "which", lambda _name: None)

    pages = diagnostics.cloudflare_environment_status(
        active=True,
        command_runner=lambda _argv, _timeout: diagnostics.CommandResult(127, "", "missing"),
        env={
            "RUMI_CLOUDFLARE_PC_TOOL_BRIDGE_URL": "https://rumi.pages.dev",
            "RUMI_PC_TOOL_BRIDGE_TOKEN": "client-secret",
            "RUMI_PC_RUNTIME_BEARER": "pc-runtime-secret",
            "RUMI_PC_ORIGIN": "https://rumi-pc.example.com",
        },
    )
    private_pc_origin = diagnostics.cloudflare_environment_status(
        active=True,
        command_runner=lambda _argv, _timeout: diagnostics.CommandResult(127, "", "missing"),
        env={
            "RUMI_CLOUDFLARE_PC_TOOL_BRIDGE_URL": "https://rumi-tool.example.workers.dev",
            "RUMI_PC_TOOL_BRIDGE_TOKEN": "client-secret",
            "RUMI_PC_RUNTIME_BEARER": "pc-runtime-secret",
            "RUMI_PC_ORIGIN": "http://192.168.1.20:8765",
        },
    )
    missing_secret = diagnostics.cloudflare_environment_status(
        active=True,
        command_runner=lambda _argv, _timeout: diagnostics.CommandResult(127, "", "missing"),
        env={
            "RUMI_CLOUDFLARE_PC_TOOL_BRIDGE_URL": "https://rumi-tool.example.workers.dev",
            "RUMI_PC_RUNTIME_BEARER": "pc-runtime-secret",
            "RUMI_PC_ORIGIN": "https://rumi-pc.example.com",
        },
    )

    assert pages["checks"]["pc_tool_bridge_env"]["status"] == "pages_dev_not_supported"
    assert private_pc_origin["checks"]["pc_tool_bridge_env"]["status"] == "invalid_pc_origin"
    assert missing_secret["checks"]["pc_tool_bridge_env"]["status"] == "bridge_token_missing"


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
