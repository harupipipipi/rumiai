from __future__ import annotations

import importlib
import json
import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _pack_api_sibling_module(handler_cls, module_name: str):
    package_name = handler_cls._dispatch_api_route.__globals__.get("__package__")
    if not package_name:
        package_name = handler_cls.__module__.rsplit(".", 1)[0]
    if package_name.endswith(".api"):
        package_name = package_name.rsplit(".", 1)[0]
    return importlib.import_module(f"{package_name}.{module_name}")


class TestDefaultspackApiRoutes(unittest.TestCase):
    def test_defaultspack_ecosystem_routes_are_loaded(self):
        from core_runtime.pack_api_server import PackAPIHandler

        ecosystem_path = (
            Path(__file__).resolve().parent.parent
            / "ecosystem"
            / "defaultspack"
            / "ecosystem.json"
        )
        data = json.loads(ecosystem_path.read_text(encoding="utf-8"))
        pack_root = ecosystem_path.parent

        class _PackInfo:
            ecosystem = data
            path = pack_root
            subdir = pack_root

        class _Registry:
            packs = {"defaultspack": _PackInfo()}

        count = PackAPIHandler.load_api_routes(_Registry(), pack_ids={"defaultspack"})
        self.assertEqual(count, 16)
        self.assertIn(("GET", "/api/defaultspack/modules"), PackAPIHandler._api_route_exact)
        self.assertIn(("GET", "/api/defaultspack/pack-requests"), PackAPIHandler._api_route_exact)
        self.assertIn(("GET", "/api/tools/mcp"), PackAPIHandler._api_route_exact)
        self.assertIn(("POST", "/api/tools/mcp/connect"), PackAPIHandler._api_route_exact)
        self.assertEqual(
            PackAPIHandler._api_route_exact[("GET", "/api/defaultspack/modules")]["function_id"],
            "list_modules",
        )
        self.assertEqual(
            PackAPIHandler._api_route_exact[("GET", "/api/tools/mcp")]["function_id"],
            "tool_mcp_list",
        )
        self.assertEqual(
            PackAPIHandler._api_route_exact[("POST", "/api/tools/mcp/connect")]["function_id"],
            "tool_mcp_connect",
        )
        self.assertEqual(len(PackAPIHandler._api_route_patterns), 9)

    def test_untrusted_function_api_routes_are_not_loaded(self):
        from core_runtime.pack_api_server import PackAPIHandler

        class _PackInfo:
            ecosystem = {
                "api_routes": [
                    {
                        "method": "POST",
                        "path": "/api/evil/run",
                        "function_id": "run",
                    }
                ]
            }

        class _Registry:
            packs = {"evil_pack": _PackInfo()}

        count = PackAPIHandler.load_api_routes(_Registry(), pack_ids={"evil_pack"})

        self.assertEqual(count, 0)
        self.assertNotIn(("POST", "/api/evil/run"), PackAPIHandler._api_route_exact)

    def test_api_route_dispatches_pack_function(self):
        from core_runtime.pack_api_server import PackAPIHandler

        PackAPIHandler._api_route_exact = {
            ("POST", "/api/example/run"): {
                "pack_id": "example",
                "handler": "",
                "function_id": "run",
                "pass_body": True,
                "response_mode": "result",
                "args": {"mode": "fast"},
                "path_param_map": {},
            }
        }
        PackAPIHandler._api_route_patterns = []
        handler = PackAPIHandler.__new__(PackAPIHandler)
        sent = []
        handler._send_result = sent.append
        execute = MagicMock(return_value=SimpleNamespace(success=True, output={"ok": True}))

        capability_executor = _pack_api_sibling_module(PackAPIHandler, "capability_executor")
        with patch.object(
            capability_executor,
            "get_capability_executor",
            return_value=SimpleNamespace(execute=execute),
        ):
            dispatched = handler._dispatch_api_route(
                "POST", "/api/example/run", {"input": "hello"}
            )

        self.assertTrue(dispatched)
        execute.assert_called_once_with(
            "example",
            {
                "type": "function.call",
                "qualified_name": "example:run",
                "args": {"mode": "fast", "input": "hello"},
                "request_id": "api-route:POST:/api/example/run",
                "context": {
                    "pack_id": "example",
                    "method": "POST",
                    "path": "/api/example/run",
                    "_api_route": True,
                },
            },
        )
        self.assertEqual(sent, [{"ok": True}])

    def test_api_route_keeps_route_args_over_body(self):
        from core_runtime.pack_api_server import PackAPIHandler

        route_entry = {
            "pack_id": "defaultspack",
            "handler": "",
            "function_id": "review_pack_request",
            "pass_body": True,
            "response_mode": "result",
            "args": {"decision": "approve"},
            "path_param_map": {"request_id": "id"},
        }
        PackAPIHandler._api_route_exact = {}
        PackAPIHandler._api_route_patterns = [
            (
                "POST",
                re.compile(r"^/api/defaultspack/pack-requests/(?P<id>[^/]+)/approve$"),
                ["id"],
                route_entry,
            )
        ]
        handler = PackAPIHandler.__new__(PackAPIHandler)
        handler._send_result = lambda result: None
        execute = MagicMock(return_value=SimpleNamespace(success=True, output={"ok": True}))

        capability_executor = _pack_api_sibling_module(PackAPIHandler, "capability_executor")
        with patch.object(
            capability_executor,
            "get_capability_executor",
            return_value=SimpleNamespace(execute=execute),
        ):
            dispatched = handler._dispatch_api_route(
                "POST",
                "/api/defaultspack/pack-requests/123/approve",
                {
                    "decision": "reject",
                    "decision_notes": "nope",
                    "request_id": "body-value",
                },
            )

        self.assertTrue(dispatched)
        execute.assert_called_once_with(
            "defaultspack",
            {
                "type": "function.call",
                "qualified_name": "defaultspack:review_pack_request",
                "args": {
                    "decision": "approve",
                    "decision_notes": "nope",
                    "request_id": "123",
                },
                "request_id": "api-route:POST:/api/defaultspack/pack-requests/123/approve",
                "context": {
                    "pack_id": "defaultspack",
                    "method": "POST",
                    "path": "/api/defaultspack/pack-requests/123/approve",
                    "_api_route": True,
                },
            },
        )

    def test_api_route_function_permission_denial_sends_forbidden(self):
        from core_runtime.pack_api_server import PackAPIHandler
        from core_runtime.api.api_response import APIResponse

        PackAPIHandler._api_route_exact = {
            ("POST", "/api/tools/mcp/connect"): {
                "pack_id": "defaultspack",
                "handler": "",
                "function_id": "tool_mcp_connect",
                "pass_body": True,
                "response_mode": "result",
                "args": {},
                "path_param_map": {},
            }
        }
        PackAPIHandler._api_route_patterns = []
        handler = PackAPIHandler.__new__(PackAPIHandler)
        sent = []
        handler._send_response = lambda response, status=200: sent.append((response, status))
        execute = MagicMock(
            return_value=SimpleNamespace(
                success=False,
                error="Caller does not meet caller_requires",
                error_type="caller_requires_denied",
            )
        )

        capability_executor = _pack_api_sibling_module(PackAPIHandler, "capability_executor")
        with patch.object(
            capability_executor,
            "get_capability_executor",
            return_value=SimpleNamespace(execute=execute),
        ):
            dispatched = handler._dispatch_api_route(
                "POST",
                "/api/tools/mcp/connect",
                {"server_name": "untrusted"},
            )

        self.assertTrue(dispatched)
        self.assertEqual(sent, [(APIResponse(False, error="Caller does not meet caller_requires"), 403)])

    def test_api_route_function_not_found_falls_back_to_legacy_route(self):
        from core_runtime.pack_api_server import PackAPIHandler

        PackAPIHandler._api_route_exact = {
            ("POST", "/api/example/run"): {
                "pack_id": "example",
                "handler": "",
                "function_id": "run",
                "pass_body": True,
                "response_mode": "result",
                "args": {},
                "path_param_map": {},
            }
        }
        PackAPIHandler._api_route_patterns = []
        handler = PackAPIHandler.__new__(PackAPIHandler)
        handler._send_response = MagicMock()
        execute = MagicMock(
            return_value=SimpleNamespace(
                success=False,
                error="Function not found: example:run",
                error_type="function_not_found",
            )
        )

        capability_executor = _pack_api_sibling_module(PackAPIHandler, "capability_executor")
        with patch.object(
            capability_executor,
            "get_capability_executor",
            return_value=SimpleNamespace(execute=execute),
        ):
            dispatched = handler._dispatch_api_route("POST", "/api/example/run", {"input": "hello"})

        self.assertFalse(dispatched)
        handler._send_response.assert_not_called()


if __name__ == "__main__":
    unittest.main()
