"""Mobile manifest for app-side route and template discovery."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok
from domain.mobile.contract import iter_mobile_route_contracts, mobile_capability_flags, mobile_feature_enabled


def _route_entry(route) -> dict:
    return {
        "method": route.method,
        "path": route.pattern,
        "feature": route.feature,
        "device_scope": route.device_scope,
        "pc_equivalent": route.pc_equivalent,
    }


def run(input_data, context=None):
    del input_data, context
    routes = [
        _route_entry(route)
        for route in iter_mobile_route_contracts()
        if route.pattern.startswith("/api/mobile/v1/")
        and not route.feature.startswith("pairing_admin")
    ]
    return ok(
        {
            "kind": "rumi_mobile_manifest_v1",
            "version": 1,
            "capabilities": mobile_capability_flags(),
            "token_roles": {
                "mobile_client": {
                    "audience": "mobile_facade",
                    "scopes": [
                        "chat.read",
                        "chat.write",
                        "tools.observe",
                        *(
                            ["credentials.request"]
                            if mobile_feature_enabled("credential_transfer")
                            else []
                        ),
                    ],
                },
                "mobile_approver": {
                    "audience": "authority",
                    "scopes": [
                        "authority.request.list",
                        "authority.request.read",
                        "authority.request.approve",
                        "authority.request.deny",
                    ],
                },
            },
            "routes": routes,
            "authority_routes": [],
            "template_sources": [
                {
                    "id": "defaultspack.templates",
                    "route": "/api/mobile/v1/capabilities?include_templates=true",
                }
            ],
        }
    )
