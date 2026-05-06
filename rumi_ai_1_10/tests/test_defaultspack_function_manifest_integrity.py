from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from core_runtime.function_registry import FunctionRegistry  # noqa: E402
from domain.function_runtime.manifest_factory import FUNCTION_SPECS_BY_ID  # noqa: E402
from domain.function_runtime.security import HIGH_RISK_CALLER_REQUIREMENT  # noqa: E402


def _manifest(function_id: str) -> dict:
    path = DEFAULTSPACK_ROOT / "functions" / function_id / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_generated_defaultspack_function_manifests_are_valid():
    aliases: dict[str, str] = {}
    for function_id in FUNCTION_SPECS_BY_ID:
        function_dir = DEFAULTSPACK_ROOT / "functions" / function_id
        manifest_path = function_dir / "manifest.json"
        main_path = function_dir / "main.py"

        assert manifest_path.is_file(), function_id
        assert main_path.is_file(), function_id

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["function_id"] == function_id
        assert re.match(r"^[a-z][a-z0-9_]*$", function_id)
        assert manifest["calling_convention"] == "subprocess"
        assert manifest["entrypoint"] == "main.py:run"

        vocab_aliases = manifest.get("vocab_aliases") or []
        assert any(alias.startswith("defaults.") for alias in vocab_aliases), function_id
        assert any(alias.startswith("defaultspack.") for alias in vocab_aliases), function_id
        for alias in vocab_aliases:
            assert alias not in aliases, alias
            aliases[alias] = function_id


def test_high_risk_functions_declare_caller_requirements():
    high_risk = [
        manifest
        for manifest in (_manifest(function_id) for function_id in FUNCTION_SPECS_BY_ID)
        if manifest.get("risk") == "high"
    ]
    assert high_risk
    for manifest in high_risk:
        assert manifest.get("requires"), manifest["function_id"]
        assert HIGH_RISK_CALLER_REQUIREMENT in manifest.get("caller_requires", []), manifest["function_id"]


def test_function_registry_resolves_defaultspack_aliases():
    registry = FunctionRegistry()
    for function_id in ("ai_set_thinking_level", "chat_send", "coding_file_read"):
        function_dir = DEFAULTSPACK_ROOT / "functions" / function_id
        registry.register(
            pack_id="defaultspack",
            function_id=function_id,
            manifest=_manifest(function_id),
            function_dir=function_dir,
        )

    assert registry.resolve_by_alias("defaults.ai.set_thinking_level").qualified_name == "defaultspack:ai_set_thinking_level"
    assert registry.resolve_by_alias("defaultspack.chat.send").qualified_name == "defaultspack:chat_send"
    assert registry.resolve_by_alias("defaults.coding.file_read").qualified_name == "defaultspack:coding_file_read"
