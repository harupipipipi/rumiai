from __future__ import annotations

import json
from urllib.parse import urlparse

from ecosystem.defaultspack.backend.sandbox.guest.protocol import GuestExecRequest
from ecosystem.defaultspack.backend.sandbox.models import (
    FilesystemPolicy,
    LifecyclePolicy,
    NetworkPolicy,
    ResourceLimits,
    RuntimeRequirements,
    SandboxCreateSpec,
    SecretsPolicy,
    WorkspaceBinding,
    ResolvedSandboxTemplate,
)
from ecosystem.defaultspack.backend.sandbox.providers.cloudflare_bridge import (
    BridgeResponse,
    CLOUDFLARE_BRIDGE_CAPABILITIES,
    CloudflareSandboxBridgeProvider,
)


class FakeBridgeTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, method, url, body, headers, timeout):
        path = urlparse(url).path
        self.calls.append(
            {
                "method": method,
                "url": url,
                "path": path,
                "body": body,
                "headers": dict(headers),
                "timeout": timeout,
            }
        )
        if method == "GET" and path == "/health":
            return BridgeResponse(200, {"content-type": "application/json"}, b'{"ok":true}')
        if method == "POST" and path == "/v1/sandbox":
            return BridgeResponse(200, {"content-type": "application/json"}, b'{"id":"cf-1"}')
        if method == "GET" and path == "/v1/sandbox/cf-1/running":
            return BridgeResponse(200, {"content-type": "application/json"}, b'{"running":true}')
        if method == "POST" and path == "/v1/sandbox/cf-1/exec":
            stream = (
                "event: stdout\n"
                "data: aGVsbG8K\n\n"
                "event: stderr\n"
                "data: d2Fybg==\n\n"
                "event: exit\n"
                "data: {\"exit_code\": 7}\n\n"
            )
            return BridgeResponse(200, {"content-type": "text/event-stream"}, stream.encode())
        if method == "PUT" and path == "/v1/sandbox/cf-1/file/src/app.py":
            return BridgeResponse(200, {"content-type": "application/json"}, b'{"ok":true}')
        if method == "GET" and path == "/v1/sandbox/cf-1/file/src/app.py":
            return BridgeResponse(200, {"content-type": "application/octet-stream"}, b"one\ntwo\nthree\n")
        if method == "DELETE" and path == "/v1/sandbox/cf-1":
            return BridgeResponse(204, {}, b"")
        return BridgeResponse(404, {}, b"not found")


class StaticBridgeTransport:
    def __init__(self, response: BridgeResponse) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def __call__(self, method, url, body, headers, timeout):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "body": body,
                "headers": dict(headers),
                "timeout": timeout,
            }
        )
        return self.response


class FailingBridgeTransport:
    def __init__(self, error: OSError) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    def __call__(self, method, url, body, headers, timeout):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "body": body,
                "headers": dict(headers),
                "timeout": timeout,
            }
        )
        raise self.error


def test_cloudflare_sandbox_bridge_doctor_requires_bridge_url(monkeypatch):
    monkeypatch.delenv("RUMI_CLOUDFLARE_SANDBOX_BRIDGE_URL", raising=False)
    monkeypatch.delenv("RUMI_CLOUDFLARE_SANDBOX_API_KEY", raising=False)
    provider = CloudflareSandboxBridgeProvider(transport=FakeBridgeTransport())

    status = provider.doctor(RuntimeRequirements(required_capabilities=frozenset({"sandbox.exec"})))

    assert status.provider_id == "cloudflare_sandbox_bridge"
    assert status.ready is False
    assert "env:RUMI_CLOUDFLARE_SANDBOX_BRIDGE_URL" in status.missing_requirements
    assert status.capabilities == frozenset()


def test_cloudflare_sandbox_bridge_doctor_rejects_unsupported_capabilities():
    transport = FakeBridgeTransport()
    provider = CloudflareSandboxBridgeProvider(
        base_url="http://localhost:8787",
        transport=transport,
    )

    status = provider.doctor(RuntimeRequirements(required_capabilities=frozenset({"sandbox.desktop"})))

    assert status.ready is False
    assert "sandbox.desktop" in status.missing_requirements
    assert status.capabilities == CLOUDFLARE_BRIDGE_CAPABILITIES


def test_cloudflare_sandbox_bridge_doctor_rejects_non_loopback_http_with_api_key():
    transport = FakeBridgeTransport()
    provider = CloudflareSandboxBridgeProvider(
        base_url="http://bridge.example.com",
        api_key="secret",
        transport=transport,
    )

    status = provider.doctor(RuntimeRequirements(required_capabilities=frozenset({"sandbox.exec"})))

    assert status.ready is False
    assert "cloudflare_sandbox_bridge_https" in status.missing_requirements
    assert any(item.code == "CLOUDFLARE_SANDBOX_BRIDGE_INSECURE_URL" for item in status.diagnostics)
    assert not transport.calls


def test_cloudflare_sandbox_bridge_exec_file_write_and_destroy_contract():
    transport = FakeBridgeTransport()
    provider = CloudflareSandboxBridgeProvider(
        base_url="https://bridge.example.com",
        api_key="secret",
        transport=transport,
    )
    template = _template()

    status = provider.doctor(RuntimeRequirements(required_capabilities=template.provider_requirements))
    created = provider.create(SandboxCreateSpec(name="Cloud", template=template, workspace_binding=WorkspaceBinding()))
    started = provider.start(created)
    agent = provider.connect_agent(started)
    exec_result = agent.exec(
        started.sandbox_id,
        GuestExecRequest(
            argv=("python", "-c", "print('hello')"),
            cwd="src",
            env={},
            timeout_ms=1000,
            stdin=None,
            client_request_id="req-1",
        ).to_agent_payload(),
    )
    file_result = agent.apply_file_patch(
        started.sandbox_id,
        {"files": [{"path": "src/app.py", "content": "print('hi')\n"}]},
    )
    read_result = agent.read_file(
        started.sandbox_id,
        {"path": "src/app.py", "start_line": 2, "end_line": 3, "max_chars": 7},
    )
    provider.destroy(started)

    assert status.ready is True
    assert started.state == "ready"
    assert exec_result["ok"] is True
    assert exec_result["exit_code"] == 7
    assert exec_result["stdout"] == "hello\n"
    assert exec_result["stderr"] == "warn"
    assert exec_result["provider_runtime"] == "cloudflare_sandbox_bridge"
    assert file_result["ok"] is True
    assert file_result["files_written"] == 1
    assert read_result["ok"] is True
    assert read_result["path"] == "src/app.py"
    assert read_result["content"] == "two\nthr"
    assert read_result["start_line"] == 2
    assert read_result["end_line"] == 3
    assert read_result["total_lines"] == 3
    assert read_result["truncated"] is True
    assert read_result["omitted_chars"] == 3
    assert any(call["method"] == "DELETE" and call["path"] == "/v1/sandbox/cf-1" for call in transport.calls)

    exec_call = next(call for call in transport.calls if call["method"] == "POST" and call["path"] == "/v1/sandbox/cf-1/exec")
    assert exec_call["headers"]["authorization"] == "Bearer secret"
    assert json.loads(exec_call["body"].decode()) == {
        "argv": ["python", "-c", "print('hello')"],
        "cwd": "/workspace/src",
        "timeout_ms": 1000,
    }

    file_call = next(call for call in transport.calls if call["method"] == "PUT")
    assert file_call["body"] == b"print('hi')\n"
    read_call = next(call for call in transport.calls if call["method"] == "GET" and call["path"] == "/v1/sandbox/cf-1/file/src/app.py")
    assert read_call["headers"]["accept"] == "application/octet-stream"


def test_cloudflare_sandbox_bridge_exec_rejects_non_loopback_http_before_auth():
    transport = StaticBridgeTransport(BridgeResponse(200, {"content-type": "text/event-stream"}, b""))
    agent = CloudflareSandboxBridgeProvider(
        base_url="http://bridge.example.com",
        api_key="secret",
        transport=transport,
    ).connect_agent(_provider_instance("cf-1"))

    result = agent.exec(
        "cf-1",
        GuestExecRequest(
            argv=("true",),
            cwd=".",
            env={},
            timeout_ms=1000,
            stdin=None,
            client_request_id="insecure-1",
        ).to_agent_payload(),
    )

    assert result["ok"] is False
    assert result["code"] == "CLOUDFLARE_SANDBOX_BRIDGE_INSECURE_URL"
    assert not transport.calls


def test_cloudflare_sandbox_bridge_http_error_redacts_bridge_api_key():
    api_key = "bridge-secret-token"
    transport = StaticBridgeTransport(
        BridgeResponse(
            502,
            {"content-type": "text/plain"},
            (
                "upstream rejected Authorization: Bearer unrelated-token "
                "and echoed bridge-secret-token"
            ).encode(),
        )
    )
    agent = CloudflareSandboxBridgeProvider(
        base_url="https://bridge.example.com",
        api_key=api_key,
        transport=transport,
    ).connect_agent(_provider_instance("cf-1"))

    result = agent.exec(
        "cf-1",
        GuestExecRequest(
            argv=("true",),
            cwd=".",
            env={},
            timeout_ms=1000,
            stdin=None,
            client_request_id="http-redact-1",
        ).to_agent_payload(),
    )

    assert result["ok"] is False
    assert result["code"] == "CLOUDFLARE_SANDBOX_BRIDGE_HTTP_ERROR"
    body = result["details"]["body"]
    assert api_key not in body
    assert "unrelated-token" not in body
    assert "Bearer [REDACTED]" in body
    assert body.count("[REDACTED]") == 2


def test_cloudflare_sandbox_bridge_os_error_redacts_bridge_api_key():
    api_key = "bridge-secret-token"
    transport = FailingBridgeTransport(
        OSError(
            "connect failed with Authorization: Bearer unrelated-token "
            "and raw bridge-secret-token"
        )
    )
    agent = CloudflareSandboxBridgeProvider(
        base_url="https://bridge.example.com",
        api_key=api_key,
        transport=transport,
    ).connect_agent(_provider_instance("cf-1"))

    result = agent.exec(
        "cf-1",
        GuestExecRequest(
            argv=("true",),
            cwd=".",
            env={},
            timeout_ms=1000,
            stdin=None,
            client_request_id="os-redact-1",
        ).to_agent_payload(),
    )

    assert result["ok"] is False
    assert result["code"] == "CLOUDFLARE_SANDBOX_BRIDGE_UNREACHABLE"
    error = result["details"]["error"]
    assert api_key not in error
    assert "unrelated-token" not in error
    assert "Bearer [REDACTED]" in error
    assert error.count("[REDACTED]") == 2


def test_cloudflare_sandbox_bridge_exec_fails_closed_for_malformed_sse():
    stream = "event: stdout\ndata: @@@\n\n"
    transport = StaticBridgeTransport(
        BridgeResponse(200, {"content-type": "text/event-stream"}, stream.encode())
    )
    agent = CloudflareSandboxBridgeProvider(
        base_url="https://bridge.example.com",
        api_key="secret",
        transport=transport,
    ).connect_agent(_provider_instance("cf-1"))

    result = agent.exec(
        "cf-1",
        GuestExecRequest(
            argv=("true",),
            cwd=".",
            env={},
            timeout_ms=1000,
            stdin=None,
            client_request_id="bad-sse-1",
        ).to_agent_payload(),
    )

    assert result["ok"] is False
    assert result["code"] == "CLOUDFLARE_SANDBOX_BRIDGE_INVALID_SSE"


def test_cloudflare_sandbox_bridge_exec_applies_provider_output_limit():
    stream = (
        "event: stdout\n"
        "data: YWJjZGVmZ2g=\n\n"
        "event: stderr\n"
        "data: MTIzNDU2Nzg=\n\n"
        "event: exit\n"
        "data: {\"exit_code\": 0}\n\n"
    )
    transport = StaticBridgeTransport(
        BridgeResponse(200, {"content-type": "text/event-stream"}, stream.encode())
    )
    agent = CloudflareSandboxBridgeProvider(
        base_url="https://bridge.example.com",
        api_key="secret",
        transport=transport,
    ).connect_agent(_provider_instance("cf-1", output_bytes=3))

    result = agent.exec(
        "cf-1",
        GuestExecRequest(
            argv=("true",),
            cwd=".",
            env={},
            timeout_ms=1000,
            stdin=None,
            client_request_id="limit-1",
        ).to_agent_payload(),
    )

    assert result["ok"] is True
    assert result["stdout"] == "abc"
    assert result["stderr"] == "123"
    assert result["stdout_truncated"] is True
    assert result["stderr_truncated"] is True


def test_cloudflare_sandbox_bridge_exec_fails_closed_for_unsupported_env_and_stdin():
    agent = CloudflareSandboxBridgeProvider(
        base_url="http://localhost:8787",
        transport=FakeBridgeTransport(),
    ).connect_agent(_provider_instance("cf-1"))

    env_result = agent.exec(
        "cf-1",
        GuestExecRequest(
            argv=("env",),
            cwd=".",
            env={"TOKEN": "secret"},
            timeout_ms=1000,
            stdin=None,
            client_request_id="env-1",
        ).to_agent_payload(),
    )
    stdin_result = agent.exec(
        "cf-1",
        GuestExecRequest(
            argv=("cat",),
            cwd=".",
            env={},
            timeout_ms=1000,
            stdin="hello",
            client_request_id="stdin-1",
        ).to_agent_payload(),
    )

    assert env_result["ok"] is False
    assert env_result["code"] == "CLOUDFLARE_SANDBOX_BRIDGE_ENV_UNSUPPORTED"
    assert stdin_result["ok"] is False
    assert stdin_result["code"] == "CLOUDFLARE_SANDBOX_BRIDGE_STDIN_UNSUPPORTED"


def test_cloudflare_sandbox_bridge_marks_pc_local_surfaces_unsupported():
    agent = CloudflareSandboxBridgeProvider(
        base_url="http://localhost:8787",
        transport=FakeBridgeTransport(),
    ).connect_agent(_provider_instance("cf-1"))

    port_result = agent.expose_port("cf-1", {"port": 5173})
    frame_result = agent.capture_frame("cf-1", "seat-1")
    input_result = agent.desktop_input("cf-1", "seat-1", {"type": "click"})

    assert port_result["ok"] is False
    assert port_result["code"] == "CLOUDFLARE_SANDBOX_BRIDGE_PORT_UNSUPPORTED"
    assert frame_result["ok"] is False
    assert frame_result["code"] == "SANDBOX_DESKTOP_NOT_AVAILABLE"
    assert input_result["ok"] is False
    assert input_result["code"] == "SANDBOX_DESKTOP_NOT_AVAILABLE"


def test_defaultspack_runtime_provider_list_includes_cloudflare_bridge(monkeypatch):
    monkeypatch.delenv("RUMI_CLOUDFLARE_SANDBOX_BRIDGE_URL", raising=False)
    from ecosystem.defaultspack.blocks.sandbox.api import _SandboxApiService, _runtime_providers

    service = _SandboxApiService(start_lifecycle_sweeper=False)

    try:
        providers = _runtime_providers(service)["providers"]
    finally:
        service.close()

    cloudflare = next(provider for provider in providers if provider["provider_id"] == "cloudflare_sandbox_bridge")
    assert cloudflare["label"] == "Cloudflare Sandbox Bridge"
    assert cloudflare["ready"] is False
    assert cloudflare["isolation"]["mode"] == "cloudflare_pending"
    assert any(item["code"] == "env:RUMI_CLOUDFLARE_SANDBOX_BRIDGE_URL" for item in cloudflare["missing"])


def _template() -> ResolvedSandboxTemplate:
    return ResolvedSandboxTemplate(
        template_id="tool.ephemeral",
        template_version="1.0.0",
        runtime_os="linux",
        provider_requirements=frozenset({"sandbox.exec", "sandbox.files", "sandbox.resource_limits"}),
        packages=(),
        desktop=None,
        filesystem=FilesystemPolicy(),
        network=NetworkPolicy(),
        secrets=SecretsPolicy(),
        resources=ResourceLimits(output_bytes=262144, timeout_ms=300000),
        lifecycle=LifecyclePolicy(ttl_seconds=300, persistent=False, destroy_on_exit=True),
        allowed_operations=frozenset({"sandbox.exec.argv"}),
        source_template_ids=("tool.ephemeral",),
    )


def _provider_instance(sandbox_id: str, *, output_bytes: int | None = None):
    from ecosystem.defaultspack.backend.sandbox.models import ProviderInstance
    from ecosystem.defaultspack.backend.sandbox.models import model_to_dict

    resources = ResourceLimits(output_bytes=output_bytes) if output_bytes is not None else ResourceLimits()

    return ProviderInstance(
        provider_id="cloudflare_sandbox_bridge",
        provider_instance_id=sandbox_id,
        sandbox_id=sandbox_id,
        runtime_id="cloudflare-sandbox-bridge",
        state="ready",
        opaque_state={"bridge_sandbox_id": sandbox_id, "resource_limits": model_to_dict(resources)},
    )
