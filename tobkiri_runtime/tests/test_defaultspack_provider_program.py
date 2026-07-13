from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_required_provider_program_has_one_canonical_registry_owner():
    from domain.ai_client.provider_program import provider_program_manifests
    from domain.ai_client.providers import validate_provider_program_coverage

    manifests = provider_program_manifests()

    assert len(manifests) == 79
    assert validate_provider_program_coverage() == []
    assert all(manifest["models"] == [] for manifest in manifests.values())
