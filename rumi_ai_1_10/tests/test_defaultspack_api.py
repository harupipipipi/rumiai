from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


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

        with patch.object(
            PackAPIHandler,
            "_is_pack_approved_for_runtime_routes",
            return_value=True,
        ):
            count = PackAPIHandler.load_api_routes(_Registry(), pack_ids={"defaultspack"})
        self.assertEqual(count, 16)
        self.assertIn(("GET", "/api/defaultspack/modules"), PackAPIHandler._api_route_exact)
        self.assertIn(("GET", "/api/defaultspack/pack-requests"), PackAPIHandler._api_route_exact)
        self.assertIn(("GET", "/api/tools/mcp"), PackAPIHandler._api_route_exact)
        self.assertIn(("POST", "/api/tools/mcp/connect"), PackAPIHandler._api_route_exact)
        self.assertEqual(
            PackAPIHandler._api_route_exact[("GET", "/api/defaultspack/modules")]["function_id"],
            "management_list_modules",
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

    def test_api_route_blocks_untrusted_pack_function_dispatch(self):
        from core_runtime.pack_api_server import PackAPIHandler

        PackAPIHandler._api_route_exact = {
            ("POST", "/api/evil/run"): {
                "pack_id": "evil_pack",
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
        sent = []
        handler._send_response = lambda response, status_code=200: sent.append((status_code, response))

        executor = SimpleNamespace(
            execute=Mock(
                return_value=SimpleNamespace(
                    success=False,
                    error="denied",
                    error_type="permission_denied",
                )
            )
        )
        with patch("core_runtime.pack_function_runtime.invoke_pack_function") as mocked:
            with patch.object(
                PackAPIHandler,
                "_is_pack_approved_for_runtime_routes",
                return_value=True,
            ), patch(
                "core_runtime.capability_executor.get_capability_executor",
                return_value=executor,
            ):
                dispatched = handler._dispatch_api_route(
                    "POST", "/api/evil/run", {"input": "hello"}
                )

        self.assertTrue(dispatched)
        mocked.assert_not_called()
        executor.execute.assert_called_once()
        self.assertEqual(sent[0][0], 403)

    def test_api_route_dispatches_pack_function(self):
        from core_runtime.pack_api_server import PackAPIHandler

        PackAPIHandler._api_route_exact = {
            ("POST", "/api/defaultspack/run"): {
                "pack_id": "defaultspack",
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

        executor = SimpleNamespace(
            execute=Mock(
                return_value=SimpleNamespace(success=True, output={"ok": True})
            )
        )
        with patch.object(
            PackAPIHandler,
            "_is_pack_approved_for_runtime_routes",
            return_value=True,
        ), patch(
            "core_runtime.capability_executor.get_capability_executor",
            return_value=executor,
        ):
            dispatched = handler._dispatch_api_route(
                "POST", "/api/defaultspack/run", {"input": "hello"}
            )

        self.assertTrue(dispatched)
        executor.execute.assert_called_once_with(
            "defaultspack",
            {
                "type": "function.call",
                "qualified_name": "defaultspack:run",
                "args": {"mode": "fast", "input": "hello"},
                "context": {
                    "pack_id": "defaultspack",
                    "method": "POST",
                    "path": "/api/defaultspack/run",
                },
            },
        )
        self.assertEqual(sent, [{"ok": True}])

    def test_api_route_keeps_route_args_over_body(self):
        from core_runtime.pack_api_server import PackAPIHandler

        route_entry = {
            "pack_id": "defaultspack",
            "handler": "",
            "function_id": "pack_request_review",
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

        executor = SimpleNamespace(
            execute=Mock(
                return_value=SimpleNamespace(success=True, output={"ok": True})
            )
        )
        with patch.object(
            PackAPIHandler,
            "_is_pack_approved_for_runtime_routes",
            return_value=True,
        ), patch(
            "core_runtime.capability_executor.get_capability_executor",
            return_value=executor,
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
        executor.execute.assert_called_once_with(
            "defaultspack",
            {
                "type": "function.call",
                "qualified_name": "defaultspack:pack_request_review",
                "args": {
                    "decision": "approve",
                    "decision_notes": "nope",
                    "request_id": "123",
                },
                "context": {
                    "pack_id": "defaultspack",
                    "method": "POST",
                    "path": "/api/defaultspack/pack-requests/123/approve",
                },
            },
        )


if __name__ == "__main__":
    unittest.main()
