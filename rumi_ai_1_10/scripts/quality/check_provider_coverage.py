from __future__ import annotations

import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MATRIX = ROOT / "provider_coverage" / "provider_matrix.json"
DEFAULT_GATE = ROOT / "provider_coverage" / "gate.json"
COMPONENT_GLOB = "ecosystem/defaultspack/domain/providers/*/manifest.json"
CATALOG_GLOB = "ecosystem/rumi_model_catalog_pack/extensions/llm/providers/*/manifest.json"
_SECRET_KEYS = {
    "api_key",
    "apikey",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "password",
    "secret",
    "headers",
}
_SECRET_VALUE = re.compile(r"(?:Bearer\s+[A-Za-z0-9._~+/-]{8,}|\bsk-[A-Za-z0-9_-]{8,})", re.IGNORECASE)


def build_report(
    *,
    root: Path = ROOT,
    matrix_path: Path = DEFAULT_MATRIX,
    cache_roots: Iterable[Path] = (),
) -> dict[str, Any]:
    matrix = _read_json(matrix_path)
    records = [item for item in matrix.get("providers", []) if isinstance(item, dict)]
    matrix_by_id = {str(item.get("provider_id") or ""): item for item in records}
    required_ids = {
        provider_id
        for provider_id, item in matrix_by_id.items()
        if item.get("completion_required") and item.get("tier") != "internal"
    }
    internal_ids = {
        provider_id for provider_id, item in matrix_by_id.items() if item.get("tier") == "internal"
    }

    manifests = _load_manifests(root)
    owners: dict[str, list[str]] = defaultdict(list)
    visible_ids: dict[str, set[str]] = defaultdict(set)
    invalid_defaults: list[dict[str, str]] = []
    for manifest in manifests:
        provider_id = manifest["provider_id"]
        owners[provider_id].append(manifest["path"])
        declared = _declared_model_ids(root / manifest["path"], manifest["payload"])
        visible_ids[provider_id].update(declared)
        default_model = str(manifest["manifest"].get("default_model") or "").strip()
        if default_model and provider_id not in internal_ids and default_model not in declared:
            invalid_defaults.append(
                {"provider_id": provider_id, "default_model": default_model, "owner": manifest["path"]}
            )

    registered = set(owners)
    authoritative = _load_authoritative_fixtures(root / "provider_coverage" / "fixtures")
    missing_visible: list[dict[str, str]] = []
    stale_visible: list[dict[str, str]] = []
    for provider_id, fixture_ids in authoritative.items():
        unified = visible_ids.get(provider_id, set())
        for model_id in sorted(fixture_ids - unified):
            missing_visible.append({"provider_id": provider_id, "model_id": model_id})
        for model_id in sorted(unified - fixture_ids):
            stale_visible.append({"provider_id": provider_id, "model_id": model_id})

    duplicates = [
        {"provider_id": provider_id, "owners": sorted(paths)}
        for provider_id, paths in sorted(owners.items())
        if len(paths) > 1 and provider_id not in internal_ids
    ]
    secret_findings = _scan_cache_roots(cache_roots)
    failures = {
        "missing_providers": sorted(required_ids - registered),
        "unmapped_registered_providers": sorted((registered - set(matrix_by_id)) - internal_ids),
        "duplicate_canonical_owners": duplicates,
        "invalid_defaults": sorted(invalid_defaults, key=lambda item: (item["provider_id"], item["owner"])),
        "missing_authoritative_model_ids": missing_visible,
        "stale_invokable_model_ids": stale_visible,
        "secret_bearing_caches": secret_findings,
    }
    failure_count = sum(len(value) for value in failures.values())
    return {
        "schema_version": 1,
        "matrix_schema_version": matrix.get("schema_version"),
        "matrix_generated_at": matrix.get("generated_at"),
        "provider_count_expected": len(records),
        "provider_count_required": len(required_ids),
        "provider_count_registered": len(registered),
        "authoritative_fixture_count": len(authoritative),
        "failure_count": failure_count,
        "passed": failure_count == 0,
        "failures": failures,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Provider Coverage Report",
        "",
        f"- Matrix date: `{report.get('matrix_generated_at')}`",
        f"- Expected providers: {report.get('provider_count_expected')}",
        f"- Required external providers: {report.get('provider_count_required')}",
        f"- Registered providers: {report.get('provider_count_registered')}",
        f"- Failures: {report.get('failure_count')}",
        f"- Result: **{'PASS' if report.get('passed') else 'REPORTING GAPS'}**",
        "",
    ]
    for key, values in report.get("failures", {}).items():
        lines.extend([f"## {key.replace('_', ' ').title()}", ""])
        if not values:
            lines.extend(["None.", ""])
            continue
        for value in values:
            lines.append(f"- `{json.dumps(value, ensure_ascii=False, sort_keys=True)}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def gate_required(gate_path: Path = DEFAULT_GATE) -> bool:
    env_value = os.environ.get("RUMI_PROVIDER_COVERAGE_REQUIRED", "").strip().lower()
    if env_value:
        return env_value in {"1", "true", "yes", "on"}
    payload = _read_json(gate_path)
    return bool(payload.get("required"))


def _load_manifests(root: Path) -> list[dict[str, Any]]:
    output = []
    for pattern in (COMPONENT_GLOB, CATALOG_GLOB):
        for path in sorted(root.glob(pattern)):
            try:
                payload = _read_json(path)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            nested = payload.get("provider_manifest") if isinstance(payload.get("provider_manifest"), dict) else payload
            provider_id = str(nested.get("id") or payload.get("provider_id") or payload.get("id") or "").strip()
            if not provider_id or nested.get("enabled") is False:
                continue
            output.append(
                {
                    "provider_id": provider_id,
                    "path": path.relative_to(root).as_posix(),
                    "payload": payload,
                    "manifest": nested,
                }
            )
    return output


def _declared_model_ids(manifest_path: Path, payload: dict[str, Any]) -> set[str]:
    model_ids: set[str] = set()

    def add_models(raw_models: Any) -> None:
        if not isinstance(raw_models, list):
            return
        for raw in raw_models:
            if isinstance(raw, dict):
                raw_model_id = str(raw.get("model_id") or "").strip()
                value = raw_model_id or str(raw.get("id") or "").strip()
            else:
                raw_model_id = ""
                value = str(raw or "").strip()
            if value:
                model_ids.add(value if raw_model_id else value.split("/", 1)[-1])

    add_models(payload.get("models"))
    entrypoints = payload.get("entrypoints") if isinstance(payload.get("entrypoints"), dict) else {}
    models_reference = str(entrypoints.get("models") or "").strip()
    if models_reference:
        referenced_path = manifest_path.parent / models_reference
        try:
            referenced = _read_json(referenced_path)
        except (OSError, ValueError, json.JSONDecodeError):
            referenced = {}
        add_models(referenced.get("models"))
    model_dir = manifest_path.parent / "models"
    if model_dir.is_dir():
        for path in sorted(model_dir.glob("*.json")):
            try:
                model = _read_json(path)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            raw_model_id = str(model.get("model_id") or "").strip()
            value = raw_model_id or str(model.get("id") or "").strip()
            if value:
                model_ids.add(value if raw_model_id else value.split("/", 1)[-1])
    return model_ids


def _load_authoritative_fixtures(path: Path) -> dict[str, set[str]]:
    output: dict[str, set[str]] = {}
    if not path.is_dir():
        return output
    for fixture_path in sorted(path.glob("*.json")):
        payload = _read_json(fixture_path)
        provider_id = str(payload.get("provider_id") or fixture_path.stem).strip()
        raw_ids = payload.get("visible_ids")
        if provider_id and isinstance(raw_ids, list):
            output[provider_id] = {str(value).strip() for value in raw_ids if str(value).strip()}
    return output


def _scan_cache_roots(cache_roots: Iterable[Path]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for root in sorted({Path(item).resolve() for item in cache_roots}, key=lambda item: str(item)):
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.json")):
            try:
                payload = _read_json(path)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            for location, reason in _secret_locations(payload):
                findings.append({"path": path.as_posix(), "location": location, "reason": reason})
    return sorted(findings, key=lambda item: (item["path"], item["location"], item["reason"]))


def _secret_locations(value: Any, location: str = "$") -> list[tuple[str, str]]:
    findings: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            child = f"{location}.{key}"
            normalized = str(key).strip().lower()
            if normalized in _SECRET_KEYS and nested not in (None, "", [], {}):
                findings.append((child, "secret_field"))
            findings.extend(_secret_locations(nested, child))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            findings.extend(_secret_locations(nested, f"{location}[{index}]"))
    elif isinstance(value, str) and _SECRET_VALUE.search(value):
        findings.append((location, "secret_value_pattern"))
    return findings


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic provider coverage reports.")
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--gate", type=Path, default=DEFAULT_GATE)
    parser.add_argument("--cache-root", action="append", type=Path, default=[])
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument("--required", action="store_true")
    args = parser.parse_args(argv)
    report = build_report(matrix_path=args.matrix, cache_roots=args.cache_root)
    json_text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(report)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json_text, encoding="utf-8", newline="\n")
    else:
        print(json_text, end="")
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(markdown, encoding="utf-8", newline="\n")
    required = args.required or gate_required(args.gate)
    return 1 if required and not report["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
