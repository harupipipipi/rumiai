from __future__ import annotations

import json

from core_runtime.setup_pack import SetupPackManager
from core_runtime.setup_pack_metadata import validate_setup_pack_schema
from ecosystem.setup_pack.pack_selector import PackSelector


def test_setup_pack_uses_generic_base_pack_promotion_metadata(tmp_path) -> None:
    root = tmp_path / "setup_pack"
    definition_path = root / "contribution_setup" / "pack.json"
    definition_path.parent.mkdir(parents=True)
    definition_path.write_text(
        json.dumps(
            {
                "pack_id": "contribution_setup",
                "target_pack_id": "contribution_pack",
                "base_pack_promotion": {"eligible": False},
            }
        ),
        encoding="utf-8",
    )

    manager = SetupPackManager(
        root=root,
        selection_file=tmp_path / "selection.json",
        ecosystem_dir=tmp_path / "ecosystem",
    )
    definition = manager.list_packs()["packs"][0]

    assert definition["base_pack_promotion"] == {"eligible": False}
    assert not validate_setup_pack_schema(
        json.loads(definition_path.read_text(encoding="utf-8"))
    )


def test_selector_reads_only_generic_base_pack_promotion_metadata(tmp_path) -> None:
    """Legacy named promotion metadata cannot restore a core fallback."""
    setup_root = tmp_path / "setup_pack"
    manifest = setup_root / "contribution_setup" / "pack.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "pack_id": "contribution_setup",
                "target_pack_id": "contribution_pack",
                "base_pack_promotion": {"eligible": False},
                "defaultspack_promotion": {"eligible": True},
            }
        ),
        encoding="utf-8",
    )

    candidate = PackSelector(setup_root).scan_candidates()[0]

    assert candidate.base_pack_promotion == {"eligible": False}
    assert candidate.to_dict()["base_pack_promotion"] == {"eligible": False}
    assert "defaultspack_promotion" not in candidate.to_dict()
