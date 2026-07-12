"""Fail-closed, data-only ``rumi.pack.v3`` manifest loading."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from .canonical import content_identity
from .models import ContractResult, ContractStatus

SCHEMA_PATH = Path(__file__).parents[2] / "schemas" / "pack_manifest_v3.schema.json"


@dataclass(frozen=True)
class ManifestDiagnostic:
    """Actionable manifest validation diagnostic."""

    path: str
    message: str


def load_manifest(path: Path) -> ContractResult[Mapping[str, Any]]:
    """Read and validate a manifest without importing or executing pack code."""
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return ContractResult(
            ContractStatus.INVALID_MANIFEST,
            diagnostics=(f"$: {exc}",),
        )
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(manifest),
        key=lambda error: list(error.absolute_path),
    )
    diagnostics = tuple(
        ManifestDiagnostic(
            path="$" + "".join(f"[{item!r}]" for item in error.absolute_path),
            message=error.message,
        )
        for error in errors
    )
    if diagnostics:
        return ContractResult(
            ContractStatus.INVALID_MANIFEST,
            diagnostics=tuple(
                f"{diagnostic.path}: {diagnostic.message}"
                for diagnostic in diagnostics
            ),
        )
    normalized = dict(manifest)
    normalized["content_identity"] = content_identity(manifest)
    return ContractResult(ContractStatus.OK, value=normalized)
