#!/usr/bin/env python3
"""Generate exact executable catalogs for finite production Pack operations."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tobkiri_protocol.canonical import canonical_digest  # noqa: E402
from tobkiri_protocol.validation import validate_document  # noqa: E402


SOURCES = ROOT / "schemas" / "executable_sources.v1.json"
ECOSYSTEM = ROOT / "ecosystem"


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _text(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def _render(pack_id: str, source: dict[str, Any]) -> dict[str, Any]:
    root = ECOSYSTEM / pack_id
    manifest = json.loads((root / "pack.v4.json").read_text(encoding="utf-8"))
    contracts = json.loads((root / "contracts.v4.json").read_text(encoding="utf-8"))
    implementation = root / source["implementation_path"]
    digest = _file_digest(implementation)
    functions = [item for item in manifest["functions"] if item["id"] == source["function_id"]]
    contract_items = [
        item for item in contracts["contracts"] if item["contract_id"] == source["contract_id"]
    ]
    if len(functions) != 1 or len(contract_items) != 1:
        raise ValueError(f"executable source does not match canonical Pack: {pack_id}")
    function = functions[0]
    contract = contract_items[0]
    if function["implementation_digest"] != digest:
        raise ValueError(f"canonical implementation digest is stale: {pack_id}")
    operation = {
        key: source[key]
        for key in (
            "contract_id",
            "contract_version",
            "operation_id",
            "input_schema",
            "output_schema",
            "error_schema",
            "effect_class",
            "timeout_default_ms",
            "timeout_hard_max_ms",
            "idempotency",
        )
    }
    operation["revision_digest"] = contract["revision_digest"]
    unsigned = {
        "catalog_api_version": "io.tobkiri.executable-catalog.v4",
        "pack_id": pack_id,
        "source_identity": manifest["integrity"]["source_identity"],
        "variants": [
            {
                key: source[key]
                for key in (
                    "variant_id",
                    "function_id",
                    "implementation_path",
                    "execution_kind",
                    "platform",
                    "architecture",
                    "runtime_abi",
                    "backend",
                    "materialization_mode",
                    "execution_domain_profile",
                )
            }
            | {"implementation_digest": digest, "operations": [operation]}
        ],
    }
    document = {**unsigned, "catalog_digest": canonical_digest(unsigned)}
    return validate_document(document, "executable_catalog")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    sources = json.loads(SOURCES.read_text(encoding="utf-8"))["packs"]
    stale: list[Path] = []
    for pack_id, source in sorted(sources.items()):
        path = ECOSYSTEM / pack_id / "executables.v4.json"
        text = _text(_render(pack_id, source))
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            stale.append(path)
            if not args.check:
                path.write_text(text, encoding="utf-8")
    if args.check and stale:
        for path in stale:
            print(path.relative_to(ROOT))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
