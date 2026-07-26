"""Compatibility specifications for contract-backed provider health."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_provider_health_projects_opaque_and_unknown_contract_state(
    monkeypatch,
) -> None:
    from domain.ai_client import provider_health

    monkeypatch.setattr(
        provider_health,
        "list_provider_catalog",
        lambda: [
            {
                "provider_id": "example",
                "display_name": "Example",
                "kind": "cloud",
                "configured": True,
            }
        ],
    )

    def invoke(contract_id, operation, payload):
        del operation, payload
        if contract_id.endswith("provider.health.v1"):
            return {
                "providers": [
                    {
                        "provider_instance_id": "provider.example",
                        "status": "unknown",
                        "observed_at": None,
                        "verified": False,
                    }
                ]
            }
        return {
            "credentials": [
                {
                    "provider_instance_id": "provider.example",
                    "handle": "credential:opaque",
                    "scopes": ["ai.generate"],
                }
            ]
        }

    monkeypatch.setattr(provider_health, "_invoke", invoke)

    report = provider_health.provider_health_report(provider_ids=["example"])
    item = report["providers"][0]
    assert report["contract_version"] == "provider-health.v2-compat"
    assert item["status"] == "unknown"
    assert item["credential"]["source"] == "opaque_handle"
    assert "secret" not in str(report).lower()


def test_provider_health_surfaces_runtime_registration_diagnostic(monkeypatch) -> None:
    from domain.ai_client import provider_health

    monkeypatch.setattr(
        provider_health,
        "list_provider_catalog",
        lambda: [
            {
                "provider_id": "broken",
                "display_name": "Broken",
                "kind": "cloud",
                "configured": True,
                "metadata": {
                    "runtime_diagnostic": {
                        "kind": "registration_error",
                        "error_type": "ImportError",
                        "message": "adapter import failed",
                    }
                },
            }
        ],
    )
    monkeypatch.setattr(
        provider_health,
        "_invoke",
        lambda contract_id, operation, payload: (
            {"providers": []}
            if contract_id.endswith("provider.health.v1")
            else {"credentials": []}
        ),
    )

    item = provider_health.provider_health_report(provider_ids=["broken"])["providers"][0]

    assert item["status"] == "registration_error"
    assert item["diagnostics"] == [
        {
            "severity": "error",
            "code": "registration_error",
            "message": "adapter import failed",
            "error_type": "ImportError",
        }
    ]
