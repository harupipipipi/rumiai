"""External-QA-oriented specifications for provider adapter boundaries."""

from __future__ import annotations

import pytest

from core_runtime.global_contract_dispatch import GlobalContractInvocationError
from ecosystem.rumi_provider_adapters_pack.runtime.adapter import _adapter


def test_adapter_selection_is_protocol_not_provider_specific() -> None:
    assert callable(_adapter("openai-compatible"))
    assert callable(_adapter("anthropic"))


def test_unknown_protocol_is_explicitly_incompatible() -> None:
    with pytest.raises(GlobalContractInvocationError) as exc:
        _adapter("provider-specific-name")

    assert exc.value.code == "incompatible"

