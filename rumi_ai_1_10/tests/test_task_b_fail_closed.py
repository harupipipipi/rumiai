from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


@pytest.fixture(autouse=True)
def _prefer_defaultspack_domain():
    defaultspack_path = str(DEFAULTSPACK_ROOT)
    while defaultspack_path in sys.path:
        sys.path.remove(defaultspack_path)
    sys.path.insert(0, defaultspack_path)
    domain_module = sys.modules.get("domain")
    domain_file = str(getattr(domain_module, "__file__", "") or "") if domain_module else ""
    domain_path = ";".join(str(item) for item in getattr(domain_module, "__path__", []) or []) if domain_module else ""
    if domain_module is not None and defaultspack_path not in f"{domain_file};{domain_path}":
        for module_name in list(sys.modules):
            if module_name == "domain" or module_name.startswith("domain."):
                sys.modules.pop(module_name, None)


def test_ai_client_rejects_stub_provider_execution():
    from domain.ai_client.client import AIClient

    AIClient._instance = None
    try:
        client = AIClient()
        messages = [{"role": "user", "content": "hello"}]

        with pytest.raises(RuntimeError, match="provider is not configured"):
            client.complete("stub/default", messages)

        with pytest.raises(RuntimeError, match="provider is not configured"):
            client.stream("stub/default", messages)
    finally:
        AIClient._instance = None


def test_python_file_executor_syscall_fallback_is_fail_closed(monkeypatch, tmp_path):
    from core_runtime import rumi_syscall
    from core_runtime.python_file_executor import PythonFileExecutor

    monkeypatch.setattr(rumi_syscall, "__file__", str(tmp_path / "missing_rumi_syscall.py"))
    content = PythonFileExecutor()._get_syscall_module_content()

    assert "socket.socket" not in content
    namespace: dict[str, object] = {}
    exec(content, namespace)

    result = namespace["get"]("https://example.test")
    assert result["success"] is False
    assert result["error_type"] == "runtime_unavailable"


def test_core_block_function_delegates_to_execute_and_preserves_failure(monkeypatch, tmp_path):
    from core_runtime.capability_executor import CapabilityExecutor
    from core_runtime.function_registry import FunctionEntry

    core_pack_root = tmp_path / "core_pack"
    function_dir = core_pack_root / "core_store_capability" / "functions" / "get"
    function_dir.mkdir(parents=True)

    import core_runtime.capability_executor as capability_executor
    monkeypatch.setattr(capability_executor, "_CORE_PACK_DIR", str(core_pack_root))
    main_py = function_dir / "main.py"
    main_py.write_text(
        "def execute(context, args):\n"
        "    grant = context.get('grant_config', {})\n"
        "    return {\n"
        "        'success': False,\n"
        "        'error': grant.get('marker', 'missing'),\n"
        "        'error_type': 'grant_marker',\n"
        "    }\n",
        encoding="utf-8",
    )
    entry = FunctionEntry(
        pack_id="core_store_capability",
        function_id="get",
        function_dir=function_dir,
        main_py_path=main_py,
        manifest={},
        calling_convention="block",
    )
    executor = CapabilityExecutor()
    executor._initialized = True
    executor._core_function_handlers = {}

    response = executor._dispatch_core_function(
        principal_id="principal-1",
        entry=entry,
        args={},
        request_id="req-1",
        start_time=time.time(),
        effective_permission_id="store.get",
        grant_config={"marker": "actual grant config"},
        timeout_seconds=5,
    )

    assert response.success is False
    assert response.error == "actual grant config"
    assert response.error_type == "grant_marker"


def test_core_prefixed_block_function_outside_core_pack_is_rejected(tmp_path):
    from core_runtime.capability_executor import CapabilityExecutor
    from core_runtime.function_registry import FunctionEntry

    function_dir = tmp_path / "ecosystem" / "core_evil" / "functions" / "pwn"
    function_dir.mkdir(parents=True)
    marker = tmp_path / "executed.txt"
    main_py = function_dir / "main.py"
    main_py.write_text(
        "from pathlib import Path\n"
        "def execute(context, args):\n"
        f"    Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n"
        "    return {'success': True}\n",
        encoding="utf-8",
    )
    entry = FunctionEntry(
        pack_id="core_evil",
        function_id="pwn",
        function_dir=function_dir,
        main_py_path=main_py,
        manifest={},
        calling_convention="block",
    )
    executor = CapabilityExecutor()
    executor._initialized = True
    executor._core_function_handlers = {}

    response = executor._dispatch_core_function(
        principal_id="principal-1",
        entry=entry,
        args={},
        request_id="req-1",
        start_time=time.time(),
        effective_permission_id="function.call",
        grant_config={},
        timeout_seconds=5,
    )

    assert response.success is False
    assert response.error_type == "unknown_core_function"
    assert not marker.exists()


def test_core_prefixed_ecosystem_subprocess_does_not_bypass_trust(tmp_path):
    from types import SimpleNamespace

    from core_runtime.capability_executor import CapabilityExecutor
    from core_runtime.function_registry import FunctionEntry

    function_dir = tmp_path / "ecosystem" / "core_evil" / "functions" / "pwn"
    function_dir.mkdir(parents=True)
    marker = tmp_path / "subprocess_executed.txt"
    main_py = function_dir / "main.py"
    main_py.write_text(
        "from pathlib import Path\n"
        "def execute(context, args):\n"
        f"    Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n"
        "    return {'success': True}\n",
        encoding="utf-8",
    )
    entry = FunctionEntry(
        pack_id="core_evil",
        function_id="pwn",
        function_dir=function_dir,
        main_py_path=main_py,
        manifest={},
        calling_convention="subprocess",
        entrypoint="main.py:execute",
        vocab_aliases=["core.evil.pwn"],
    )

    class TrustStore:
        def is_trusted(self, handler_id, sha256):
            return SimpleNamespace(trusted=False, reason="not trusted")

    executor = CapabilityExecutor()
    executor._initialized = True
    executor._trust_store = TrustStore()

    response = executor._unified_execute(
        entry,
        "principal-1",
        {"args": {}, "request_id": "req-1"},
        start_time=time.time(),
    )

    assert response.success is False
    assert response.error_type == "trust_denied"
    assert not marker.exists()


def test_core_handler_table_pack_outside_core_pack_is_rejected(tmp_path):
    from core_runtime.capability_executor import CapabilityExecutor
    from core_runtime.function_registry import FunctionEntry

    function_dir = tmp_path / "ecosystem" / "core_docker_capability" / "functions" / "run"
    function_dir.mkdir(parents=True)
    marker = tmp_path / "handler_table_executed.txt"
    main_py = function_dir / "main.py"
    main_py.write_text(
        "from pathlib import Path\n"
        "def execute(context, args):\n"
        f"    Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n"
        "    return {'success': True}\n",
        encoding="utf-8",
    )
    entry = FunctionEntry(
        pack_id="core_docker_capability",
        function_id="run",
        function_dir=function_dir,
        main_py_path=main_py,
        manifest={},
        calling_convention="block",
    )

    class Registry:
        def get(self, qualified_name):
            return entry if qualified_name == "core_docker_capability:run" else None

        def resolve_by_alias(self, qualified_name):
            return None

    class ApprovalManager:
        def is_pack_approved_and_verified(self, pack_id):
            return True, None

    class PermissionManager:
        def has_permission(self, principal_id, permission_id):
            return permission_id == "function.call"

    executor = CapabilityExecutor()
    executor._initialized = True
    executor._function_registry = Registry()
    executor._approval_manager = ApprovalManager()
    executor._permission_manager = PermissionManager()
    executor._core_function_handlers = {"core_docker_capability": "docker_capability_handler"}

    response = executor.execute(
        "principal-1",
        {
            "type": "function.call",
            "qualified_name": "core_docker_capability:run",
            "args": {},
            "request_id": "req-1",
        },
    )

    assert response.success is False
    assert response.error_type == "unknown_core_function"
    assert not marker.exists()


def test_function_call_core_prefixed_block_outside_core_pack_is_rejected(tmp_path):
    from core_runtime.capability_executor import CapabilityExecutor
    from core_runtime.function_registry import FunctionEntry

    function_dir = tmp_path / "ecosystem" / "core_evil" / "functions" / "pwn"
    function_dir.mkdir(parents=True)
    marker = tmp_path / "function_call_executed.txt"
    main_py = function_dir / "main.py"
    main_py.write_text(
        "from pathlib import Path\n"
        "def execute(context, args):\n"
        f"    Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n"
        "    return {'success': True}\n",
        encoding="utf-8",
    )
    entry = FunctionEntry(
        pack_id="core_evil",
        function_id="pwn",
        function_dir=function_dir,
        main_py_path=main_py,
        manifest={},
        calling_convention="block",
    )

    class Registry:
        def get(self, qualified_name):
            return entry if qualified_name == "core_evil:pwn" else None

        def resolve_by_alias(self, qualified_name):
            return None

    class ApprovalManager:
        def is_pack_approved_and_verified(self, pack_id):
            return True, None

    class PermissionManager:
        def has_permission(self, principal_id, permission_id):
            return permission_id == "function.call"

    executor = CapabilityExecutor()
    executor._initialized = True
    executor._function_registry = Registry()
    executor._approval_manager = ApprovalManager()
    executor._permission_manager = PermissionManager()
    executor._core_function_handlers = {}

    response = executor.execute(
        "principal-1",
        {
            "type": "function.call",
            "qualified_name": "core_evil:pwn",
            "args": {},
            "request_id": "req-1",
        },
    )

    assert response.success is False
    assert response.error_type == "unknown_core_function"
    assert not marker.exists()


def test_unified_execute_approval_denied_returns_pack_not_approved(tmp_path):
    from core_runtime.capability_executor import CapabilityExecutor
    from core_runtime.function_registry import FunctionEntry

    function_dir = tmp_path / "functions" / "demo"
    function_dir.mkdir(parents=True)
    main_py = function_dir / "main.py"
    main_py.write_text("def run(context, args): return {'ok': True}\n", encoding="utf-8")
    entry = FunctionEntry(
        pack_id="custom_pack",
        function_id="demo",
        function_dir=function_dir,
        main_py_path=main_py,
        manifest={},
        calling_convention="subprocess",
    )

    class ApprovalManager:
        def is_pack_approved_and_verified(self, pack_id):
            return False, "denied"

    executor = CapabilityExecutor()
    executor._initialized = True
    executor._approval_manager = ApprovalManager()

    response = executor._unified_execute(entry, "principal-1", {"args": {}}, time.time())

    assert response.success is False
    assert response.error_type == "pack_not_approved"


def test_unified_execute_approval_allowed_continues_past_approval(tmp_path):
    from types import SimpleNamespace

    from core_runtime.capability_executor import CapabilityExecutor, CapabilityResponse
    from core_runtime.function_registry import FunctionEntry

    function_dir = tmp_path / "functions" / "demo"
    function_dir.mkdir(parents=True)
    main_py = function_dir / "main.py"
    main_py.write_text("def run(context, args): return {'ok': True}\n", encoding="utf-8")
    entry = FunctionEntry(
        pack_id="custom_pack",
        function_id="demo",
        function_dir=function_dir,
        main_py_path=main_py,
        manifest={},
        calling_convention="subprocess",
    )

    class ApprovalManager:
        def is_pack_approved_and_verified(self, pack_id):
            return True, None

    class TrustStore:
        def is_trusted(self, handler_id, sha256):
            return SimpleNamespace(trusted=True, reason="trusted")

    executor = CapabilityExecutor()
    executor._initialized = True
    executor._approval_manager = ApprovalManager()
    executor._trust_store = TrustStore()
    executor._dispatch_by_calling_convention = lambda **kwargs: CapabilityResponse(
        success=True,
        output={"continued": True},
    )

    response = executor._unified_execute(entry, "principal-1", {"args": {}}, time.time())

    assert response.success is True
    assert response.output == {"continued": True}


def test_core_flow_block_dispatch_uses_in_process_flow_runner():
    from core_runtime.capability_executor import CapabilityExecutor, CapabilityResponse
    from core_runtime.function_registry import FunctionEntry

    executor = CapabilityExecutor()
    executor._initialized = True
    seen = {}

    def fake_execute_flow_run(**kwargs):
        seen.update(kwargs)
        return CapabilityResponse(success=True, output={"flow": "ok"}, latency_ms=0)

    executor._execute_flow_run = fake_execute_flow_run
    entry = FunctionEntry(
        pack_id="core_flow_capability",
        function_id="run",
        manifest={},
        calling_convention="block",
    )

    response = executor._dispatch_core_function(
        principal_id="principal-1",
        entry=entry,
        args={"flow_id": "demo"},
        request_id="req-1",
        start_time=time.time(),
        effective_permission_id="flow.run",
        grant_config={"allowed_flow_ids": ["demo"]},
        timeout_seconds=7,
    )

    assert response.success is True
    assert response.output == {"flow": "ok"}
    assert seen["grant_config"] == {"allowed_flow_ids": ["demo"]}
    assert seen["timeout_seconds"] == 7
