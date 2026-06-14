from __future__ import annotations

import importlib.util
from pathlib import Path


_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "core_runtime"
    / "core_pack"
    / "core_communication_capability"
    / "functions"
    / "propose_patch"
    / "main.py"
)


def _load_propose_patch_module():
    spec = importlib.util.spec_from_file_location("propose_patch_main_for_test", _MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_pack(tmp_path: Path) -> Path:
    pack_dir = tmp_path / "ecosystem" / "victim_pack"
    pack_dir.mkdir(parents=True)
    (pack_dir / "ecosystem.json").write_text('{"pack_id":"victim_pack"}', encoding="utf-8")
    return pack_dir


def test_propose_patch_rejects_absolute_file_path(tmp_path, monkeypatch):
    module = _load_propose_patch_module()
    pack_dir = _make_pack(tmp_path)
    marker = tmp_path / "outside_staging.txt"

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, "_find_pack_dir", lambda pack_id: pack_dir)
    monkeypatch.setattr(module, "_audit_propose_patch", lambda **kwargs: None)

    result = module.execute(
        {"principal_id": "requesting_pack", "grant_config": {}},
        {
            "target_pack_id": "victim_pack",
            "changes": [
                {"file_path": str(marker), "content": "attacker controlled"},
            ],
        },
    )

    assert result["success"] is False
    assert result["error_type"] == "validation_error"
    assert "absolute file_path" in result["error"]
    assert not marker.exists()


def test_propose_patch_writes_relative_file_inside_staging_payload(tmp_path, monkeypatch):
    module = _load_propose_patch_module()
    pack_dir = _make_pack(tmp_path)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, "_find_pack_dir", lambda pack_id: pack_dir)
    monkeypatch.setattr(module, "_audit_propose_patch", lambda **kwargs: None)

    result = module.execute(
        {"principal_id": "requesting_pack", "grant_config": {}},
        {
            "target_pack_id": "victim_pack",
            "changes": [
                {"file_path": "nested/file.txt", "content": "safe proposal"},
            ],
        },
    )

    assert result["success"] is True
    staged_file = (
        tmp_path
        / "user_data"
        / "pack_staging"
        / result["staging_id"]
        / "payload"
        / "victim_pack"
        / "nested"
        / "file.txt"
    )
    assert staged_file.read_text(encoding="utf-8") == "safe proposal"
