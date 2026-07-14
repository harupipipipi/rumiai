"""External-QA-oriented specifications for the Wave 5 model catalog."""

from __future__ import annotations

from ecosystem.rumi_model_catalog_pack.runtime.catalog import (
    CATALOG_REVISION,
    create_model_catalog_operation,
)


def test_catalog_is_provider_neutral_and_credential_free() -> None:
    operation = create_model_catalog_operation(None)
    result = operation("list", {})

    assert result["catalog_revision"] == CATALOG_REVISION
    assert result["providers"]
    assert result["models"]
    for model in result["models"]:
        assert model["execution_provider_instance_id"].startswith("provider.")
        assert "credential" not in model
        assert "adapter" not in model


def test_catalog_filter_is_finite() -> None:
    operation = create_model_catalog_operation(None)
    result = operation("list", {"provider_id": "does-not-exist"})

    assert result["providers"] == []
    assert result["models"] == []

