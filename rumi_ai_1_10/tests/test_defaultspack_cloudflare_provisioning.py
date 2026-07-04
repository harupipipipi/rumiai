from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _spec():
    from domain.cloudflare.provisioning import CloudflareRunnerSpec

    return CloudflareRunnerSpec(
        account_id="account-id",
        prefix="rumi-test",
        worker_name="rumi-test-runner",
        d1_database_name="rumi-test-state",
        r2_bucket_name="rumi-test-artifacts",
        queue_name="rumi-test-tasks",
        workflow_name="rumi-test-workflow",
        secrets={"RUMI_CALLBACK_TOKEN": "callback-secret"},
    )


class FakeCloudflareSDK:
    def __init__(self, *, existing: bool = False) -> None:
        self.existing = existing
        self.calls: list[tuple[str, object]] = []

    def list_d1_databases(self, *, account_id=None, per_page=50):
        self.calls.append(("list_d1", account_id))
        return [{"uuid": "d1-id", "name": "rumi-test-state"}] if self.existing else []

    def create_d1_database(self, name, *, account_id=None):
        self.calls.append(("create_d1", name))
        return {"uuid": "d1-id", "name": name}

    def list_r2_buckets(self, *, account_id=None, per_page=50):
        self.calls.append(("list_r2", account_id))
        return [{"name": "rumi-test-artifacts"}] if self.existing else []

    def create_r2_bucket(self, name, *, account_id=None, location=None):
        self.calls.append(("create_r2", name))
        return {"name": name}

    def list_queues(self, *, account_id=None, per_page=50):
        self.calls.append(("list_queue", account_id))
        return [{"id": "queue-id", "queue_name": "rumi-test-tasks"}] if self.existing else []

    def create_queue(self, name, *, account_id=None, **params):
        self.calls.append(("create_queue", name))
        return {"id": "queue-id", "queue_name": name}

    def list_workflows(self, *, account_id=None, per_page=50):
        self.calls.append(("list_workflow", account_id))
        return [{"id": "workflow-id", "name": "rumi-test-workflow"}] if self.existing else []

    def put_workflow(self, workflow_name, *, script_name, class_name, bindings=None, account_id=None):
        self.calls.append(("put_workflow", workflow_name))
        return {"id": "workflow-id", "name": workflow_name}

    def get_worker(self, script_name, *, account_id=None):
        self.calls.append(("get_worker", script_name))
        if not self.existing:
            from core_runtime.cloudflare.sdk_client import CloudflareSDKOperationError

            raise CloudflareSDKOperationError("missing", status_code=404)
        return {"id": "worker-id", "name": script_name}

    def upload_worker_module(self, script_name, *, main_module, modules=None, bindings=None, account_id=None):
        self.calls.append(("upload_worker", script_name))
        return {"id": "worker-id", "name": script_name, "bindings": list(bindings or [])}

    def patch_worker_settings(self, script_name, *, settings, account_id=None):
        self.calls.append(("patch_worker_settings", script_name))
        return {"name": script_name, "settings": dict(settings)}

    def patch_worker_secrets(self, script_name, secrets, *, account_id=None):
        self.calls.append(("patch_worker_secrets", sorted(secrets)))
        return [{"name": name} for name in secrets]

    def delete_worker(self, script_name, *, account_id=None):
        self.calls.append(("delete_worker", script_name))
        return {"deleted": True}

    def delete_d1_database(self, database_id, *, account_id=None):
        self.calls.append(("delete_d1", database_id))
        return {"deleted": True}

    def delete_r2_bucket(self, name, *, account_id=None):
        self.calls.append(("delete_r2", name))
        return {"deleted": True}

    def delete_queue(self, queue_id_or_name, *, account_id=None):
        self.calls.append(("delete_queue", queue_id_or_name))
        return {"deleted": True}

    def delete_workflow(self, workflow_name, *, account_id=None):
        self.calls.append(("delete_workflow", workflow_name))
        return {"deleted": True}


def test_cloudflare_connection_adapter_normalizes_context_and_redacts_sdk_errors(monkeypatch):
    from core_runtime.connections.providers.cloudflare import CLOUDFLARE_PROVIDER
    from core_runtime.connections.templates import CredentialBundle
    from domain.connections.cloudflare import CloudflareConnectionAdapter

    monkeypatch.setenv("RUMI_CLOUDFLARE_ACCOUNT_ID", "env-account")
    monkeypatch.setenv("RUMI_CLOUDFLARE_ZONE_ID", "env-zone")
    monkeypatch.setenv("RUMI_CLOUDFLARE_REQUESTED_CAPABILITIES", "cloudflare.account.read")

    bundle = CredentialBundle.from_dict(
        {
            "provider_id": "cloudflare",
            "connection_id": "default",
            "material_type": "oauth2_token",
            "credentials": {"access_token": "cloudflare-secret-token"},
            "token_metadata": {"account_id": "metadata-account"},
        }
    )
    secret_material = bundle.secret_material()
    secret_material["context"] = {"account_id": "context-account", "zone_id": "context-zone"}

    metadata = CloudflareConnectionAdapter().normalize_token_metadata(
        provider=CLOUDFLARE_PROVIDER,
        credential_bundle=bundle,
        secret_material=secret_material,
    )

    assert metadata["provider_id"] == "cloudflare"
    assert metadata["account_id"] == "metadata-account"
    assert metadata["zone_id"] == "context-zone"
    assert metadata["requested_capabilities"] == ["cloudflare.account.read"]
    assert metadata["account_id_configured"] is True
    assert metadata["zone_id_configured"] is True
    assert metadata["cloudflare_account_status"] in {"sdk_missing", "unverified", "verified"}
    assert "cloudflare-secret-token" not in str(metadata)


def test_cloudflare_runner_plan_and_dry_run_are_side_effect_free():
    from domain.cloudflare.provisioning import CloudflareRunnerProvisioner

    sdk = FakeCloudflareSDK()
    provisioner = CloudflareRunnerProvisioner(sdk=sdk, capabilities=["cloudflare.runner.deploy"])

    plan = provisioner.plan(_spec())
    dry_run = provisioner.deploy(_spec(), dry_run=True)

    assert plan["status"] == "ready"
    assert [action["resource"] for action in plan["actions"]] == ["d1", "r2", "queue", "workflow", "worker", "worker_secrets"]
    assert dry_run["dry_run"] is True
    assert sdk.calls == []


def test_cloudflare_runner_deploy_requires_capability_and_approval_before_writes():
    from domain.cloudflare.provisioning import CloudflareRunnerProvisioner

    sdk = FakeCloudflareSDK()
    missing_capability = CloudflareRunnerProvisioner(sdk=sdk, capabilities=[]).deploy(_spec())
    missing_approval = CloudflareRunnerProvisioner(
        sdk=sdk,
        capabilities=["cloudflare.runner.deploy"],
        approved_capabilities=[],
    ).deploy(_spec())

    assert missing_capability["status"] == "insufficient_capabilities"
    assert missing_approval["status"] == "approval_required"
    assert missing_approval["approval_required"] is True
    assert sdk.calls == []


def test_cloudflare_runner_deploy_order_and_idempotent_reuse():
    from domain.cloudflare.provisioning import CloudflareRunnerProvisioner

    sdk = FakeCloudflareSDK(existing=True)
    result = CloudflareRunnerProvisioner(
        sdk=sdk,
        capabilities=["cloudflare.runner.deploy"],
        approved_capabilities=["cloudflare.runner.deploy"],
    ).deploy(_spec())

    assert result["success"] is True
    assert result["status"] == "deployed"
    assert [name for name, _value in sdk.calls] == [
        "list_d1",
        "list_r2",
        "list_queue",
        "list_workflow",
        "get_worker",
        "upload_worker",
        "patch_worker_settings",
        "patch_worker_secrets",
    ]
    assert [op["operation"] for op in result["operations"]][:4] == ["reused", "reused", "reused", "reused"]
    assert "callback-secret" not in str(result)


def test_cloudflare_runner_delete_only_targets_rumi_owned_resources():
    from domain.cloudflare.provisioning import CloudflareRunnerProvisioner

    spec = _spec().__class__(
        account_id="account-id",
        prefix="rumi-test",
        worker_name="not-owned-runner",
        d1_database_name="rumi-test-state",
        r2_bucket_name="rumi-test-artifacts",
        queue_name="rumi-test-tasks",
        workflow_name="rumi-test-workflow",
    )
    sdk = FakeCloudflareSDK()
    result = CloudflareRunnerProvisioner(
        sdk=sdk,
        capabilities=["cloudflare.runner.deploy"],
        approved_capabilities=["cloudflare.runner.deploy"],
    ).delete(spec)

    assert result["success"] is True
    assert result["operations"][0]["operation"] == "skipped"
    assert ("delete_worker", "not-owned-runner") not in sdk.calls
    assert [name for name, _value in sdk.calls] == ["delete_workflow", "delete_queue", "delete_r2", "delete_d1"]


def test_cloudflare_oauth_action_ignores_client_supplied_approved(monkeypatch):
    from blocks.ai import oauth as oauth_block

    captured: dict[str, object] = {}

    def fake_action(action, *, approved_capabilities=None):
        captured["action"] = action
        captured["approved_capabilities"] = list(approved_capabilities or [])
        return {"success": False, "status": "approval_required", "approval_required": True}

    monkeypatch.setattr(oauth_block, "cloudflare_runner_provisioning_action", fake_action)

    result = oauth_block.run(
        {
            "_method": "POST",
            "provider_id": "cloudflare",
            "action": "cloudflare_deploy",
            "approved": True,
        },
        {},
    )

    assert captured == {"action": "deploy", "approved_capabilities": []}
    assert result["status"] == "error"
    assert result["error"]["code"] == "OAUTH_FAILED"
