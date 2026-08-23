"""Regression coverage for the v4 Workers Python fixed-tool route."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ecosystem.rumi_cloudflare_worker_python_pack.runtime.worker import (
    PROVIDER_INSTANCE_ID,
    WorkerResponse,
    create_definition_contribution,
    create_invoke_operation,
)
from ecosystem.rumi_tool_remote_executor_pack.runtime.executor import (
    create_execute_operation,
)

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "ecosystem" / "rumi_cloudflare_worker_python_pack"


def _payload(tool_id: str = "web_search", **values: object) -> dict[str, object]:
    return {
        "_contract_consumer_pack_id": "rumi_tool_remote_executor_pack",
        "tool_id": tool_id,
        "arguments": {"query": "Tobkiri"},
        **values,
    }


def test_worker_operation_invokes_only_configured_workers_dev_endpoint() -> None:
    captured: dict[str, object] = {}

    def transport(method, url, body, headers, timeout):
        captured.update(
            method=method,
            url=url,
            body=json.loads(body),
            headers=dict(headers),
            timeout=timeout,
        )
        return WorkerResponse(
            200,
            json.dumps({"ok": True, "result": "answer", "widget": {}}).encode(),
        )

    operation = create_invoke_operation(
        None,
        transport=transport,
        environ={
            "RUMI_CLOUDFLARE_WORKER_PYTHON_URL": "https://fixed.example.workers.dev",
            "RUMI_CLOUDFLARE_WORKER_PYTHON_API_KEY": "injected-secret",
        },
    )
    result = operation("invoke", _payload())

    assert result["is_error"] is False
    assert result["result"] == "answer"
    assert captured["url"] == "https://fixed.example.workers.dev/v1/tools/invoke"
    assert captured["body"] == {
        "tool_name": "web_search",
        "arguments": {"query": "Tobkiri"},
    }
    assert captured["headers"]["authorization"] == "Bearer injected-secret"


@pytest.mark.parametrize(
    "tool_id",
    ["python_exec", "sandbox_exec", "computer_use", "git_push", "slack_send"],
)
def test_worker_operation_rejects_nonfixed_tools_without_transport(
    tool_id: str,
) -> None:
    operation = create_invoke_operation(
        None,
        transport=lambda *_args: pytest.fail("transport must not run"),
        environ={},
    )

    result = operation("invoke", _payload(tool_id))

    assert result["is_error"] is True
    assert result["error"]["code"] == "worker_python_tool_unsupported"


def test_worker_operation_rejects_consumer_and_argument_route_injection() -> None:
    operation = create_invoke_operation(
        None,
        transport=lambda *_args: pytest.fail("transport must not run"),
        environ={
            "RUMI_CLOUDFLARE_WORKER_PYTHON_URL": "https://fixed.example.workers.dev",
            "RUMI_CLOUDFLARE_WORKER_PYTHON_API_KEY": "secret",
        },
    )
    with pytest.raises(PermissionError, match="consumer"):
        operation(
            "invoke",
            {**_payload(), "_contract_consumer_pack_id": "untrusted-pack"},
        )

    payload = _payload()
    payload["arguments"] = {
        "query": "Tobkiri",
        "provider_id": PROVIDER_INSTANCE_ID,
    }
    result = operation("invoke", payload)
    assert result["error"]["code"] == "worker_python_routing_argument_rejected"


@pytest.mark.parametrize(
    "url",
    [
        "http://fixed.example.workers.dev",
        "https://example.com",
        "https://user:password@fixed.example.workers.dev",
        "https://fixed.example.workers.dev?target=other",
        "https://fixed.example.workers.dev/other",
        "https://fixed.example.workers.dev:8443",
        "http://localhost:9999",
    ],
)
def test_worker_operation_rejects_unsealed_endpoint_shapes(url: str) -> None:
    operation = create_invoke_operation(
        None,
        transport=lambda *_args: pytest.fail("transport must not run"),
        environ={
            "RUMI_CLOUDFLARE_WORKER_PYTHON_URL": url,
            "RUMI_CLOUDFLARE_WORKER_PYTHON_API_KEY": "secret",
        },
    )
    result = operation("invoke", _payload())
    assert result["error"]["code"] == "worker_python_not_configured"


def test_definition_contribution_seals_remote_authority_and_finite_aliases() -> None:
    catalog = create_definition_contribution(None)("list", {})

    assert catalog["aliases"] == {
        "tool_reddit_search": "reddit_search",
        "tool_web_search": "web_search",
    }
    assert [item["tool_id"] for item in catalog["definitions"]] == [
        "calculator",
        "reddit_search",
        "web_search",
    ]
    for definition in catalog["definitions"]:
        assert definition["execution"] == {
            "kind": "remote",
            "contract_id": "rumi.service.tool.remote.operation.v1",
            "provider_instance_id": (
                "rumi_cloudflare_worker_python_pack."
                "cloudflare-worker-python.fixed-tools"
            ),
        }
        assert "routes" not in definition["execution"]


def test_remote_executor_uses_only_definition_sealed_provider_without_fallback() -> None:
    calls: list[tuple[str, str, dict[str, object], str | None]] = []

    class Client:
        def invoke(
            self,
            contract_id: str,
            operation_id: str,
            payload: dict[str, object],
            *,
            provider_instance_id: str | None = None,
        ) -> dict[str, object]:
            calls.append(
                (contract_id, operation_id, payload, provider_instance_id)
            )
            return {
                "result": None,
                "is_error": True,
                "error": {"code": "worker_python_unavailable"},
            }

    definition = create_definition_contribution(None)("list", {})["definitions"][2]
    result = create_execute_operation(Client())(
        "execute",
        {
            "_contract_consumer_pack_id": "rumi_tool_broker_pack",
            "tool_id": "web_search",
            "arguments": {"query": "Tobkiri"},
            "definition": definition,
            "execution_route": "caller-controlled-route",
            "provider_id": "caller-controlled-provider",
        },
    )

    assert result["error"] == {"code": "worker_python_unavailable"}
    assert len(calls) == 1
    assert calls[0][0:2] == (
        "rumi.service.tool.remote.operation.v1",
        "invoke",
    )
    assert calls[0][3] == (
        "rumi_cloudflare_worker_python_pack."
        "cloudflare-worker-python.fixed-tools"
    )
    assert "execution_route" not in calls[0][2]
    assert "provider_id" not in calls[0][2]


def test_default_profile_does_not_implicitly_activate_worker_credentials() -> None:
    profile = json.loads(
        (
            ROOT / "ecosystem" / "defaultspack" / "v4" / "defaults.profile.v4.json"
        ).read_text(encoding="utf-8")
    )

    assert "rumi_cloudflare_worker_python_pack" not in {
        item["pack_id"] for item in profile["packs"]
    }


def test_pack_metadata_pins_packvm_and_exact_effect_ceiling() -> None:
    manifest = json.loads((PACK / "pack.v4.json").read_text(encoding="utf-8"))
    executables = json.loads(
        (PACK / "executables.v4.json").read_text(encoding="utf-8")
    )

    assert manifest["requirements"]["execution_boundary"] == "sandbox"
    assert manifest["requirements"]["network"]["allowed_domains"] == [
        "*.workers.dev",
        "127.0.0.1",
        "::1",
        "localhost",
    ]
    assert manifest["requirements"]["network"]["allowed_ports"] == [443, 8787]
    assert manifest["requirements"]["secrets"] == [
        "RUMI_CLOUDFLARE_WORKER_PYTHON_API_KEY",
        "RUMI_CLOUDFLARE_WORKER_PYTHON_URL",
    ]
    assert manifest["provider_catalog"][0]["provider_id"].endswith(
        PROVIDER_INSTANCE_ID
    )
    assert {item["function_id"] for item in executables["variants"]} == {
        "rumi_cloudflare_worker_python_pack.cloudflare-worker-python.fixed-tools",
        (
            "rumi_cloudflare_worker_python_pack."
            "tool-definitions.cloudflare-worker-python"
        ),
    }
    assert {item["execution_kind"] for item in executables["variants"]} == {
        "pack_vm"
    }
    assert {item["backend"] for item in executables["variants"]} == {
        "tobkiri.python-pack-v4"
    }
