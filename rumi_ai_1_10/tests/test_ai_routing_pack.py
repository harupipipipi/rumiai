"""External-QA-oriented specifications for deterministic AI routing."""

from __future__ import annotations

from ecosystem.rumi_ai_routing_pack.runtime.router import create_route_operation


def _model(model_id: str, **overrides):
    value = {
        "model_id": model_id,
        "provider_model_id": model_id,
        "provider_id": "example",
        "execution_provider_instance_id": "provider.compatibility",
        "health_provider_instance_id": "provider.example",
        "modalities": ["text"],
        "capabilities": ["tool_calling", "thinking"],
        "context_length": 1000,
        "priority": 10,
        "available": True,
        "catalog_revision": "fixture",
    }
    value.update(overrides)
    return value


def test_router_is_deterministic_and_preserves_unknown_health() -> None:
    operation = create_route_operation(None)
    payload = {
        "models": [_model("b"), _model("a")],
        "execution_providers": [
            {"provider_instance_id": "provider.compatibility"}
        ],
        "health": {},
        "decision_time": 1000.0,
        "requirements": {"modalities": ["text"]},
    }

    first = operation("route", payload)
    second = operation("route", payload)
    assert first == second
    assert first["selected"]["model_id"] == "a"
    assert first["selected"]["health"] == "unknown"


def test_maximum_cost_rejects_unknown_cost() -> None:
    result = create_route_operation(None)(
        "route",
        {
            "models": [_model("unknown")],
            "execution_providers": [
                {"provider_instance_id": "provider.compatibility"}
            ],
            "decision_time": 1000.0,
            "requirements": {"maximum_cost": 1.0},
        },
    )

    assert result["selected"] is None
    assert result["excluded"][0]["reason"] == "cost_unknown"
