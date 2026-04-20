from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

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

        class _PackInfo:
            ecosystem = data

        class _Registry:
            packs = {"defaultspack": _PackInfo()}

        count = PackAPIHandler.load_api_routes(_Registry())
        self.assertEqual(count, 14)
        self.assertIn(("GET", "/api/defaultspack/modules"), PackAPIHandler._api_route_exact)
        self.assertIn(("GET", "/api/defaultspack/pack-requests"), PackAPIHandler._api_route_exact)
        self.assertEqual(
            PackAPIHandler._api_route_exact[("GET", "/api/defaultspack/modules")]["function_id"],
            "list_modules",
        )
        self.assertEqual(len(PackAPIHandler._api_route_patterns), 9)

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

        with patch(
            "core_runtime.pack_function_runtime.invoke_pack_function",
            return_value={"ok": True},
        ) as mocked:
            dispatched = handler._dispatch_api_route(
                "POST", "/api/example/run", {"input": "hello"}
            )

        self.assertTrue(dispatched)
        mocked.assert_called_once_with(
            "example",
            "run",
            {"mode": "fast", "input": "hello"},
            {"pack_id": "example", "method": "POST", "path": "/api/example/run"},
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

        with patch(
            "core_runtime.pack_function_runtime.invoke_pack_function",
            return_value={"ok": True},
        ) as mocked:
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
        mocked.assert_called_once_with(
            "defaultspack",
            "review_pack_request",
            {
                "decision": "approve",
                "decision_notes": "nope",
                "request_id": "123",
            },
            {
                "pack_id": "defaultspack",
                "method": "POST",
                "path": "/api/defaultspack/pack-requests/123/approve",
            },
        )


if __name__ == "__main__":
    unittest.main()
