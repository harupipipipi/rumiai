from __future__ import annotations

import hashlib
import json

from ecosystem.defaultspack.domain.templates._helpers import (
    canonical_json,
    ordered_unique_strings,
    payload_source,
    sorted_unique_strings,
    string_list,
)
from ecosystem.defaultspack.domain.templates.models import TemplateDiagnostic


def test_string_list_splits_comma_strings():
    assert string_list("a, b,,c") == ["a", "b", "c"]


def test_string_list_preserves_existing_list_semantics():
    assert string_list(["a", " a ", "", None, "b"]) == ["a", "a", "b"]


def test_ordered_unique_strings_preserves_first_seen_order():
    assert ordered_unique_strings(["b", "a", "b"]) == ["b", "a"]


def test_sorted_unique_strings_sorts_unique_values():
    assert sorted_unique_strings(["b", "a", "b"]) == ["a", "b"]


def test_payload_source_prefers_first_nested_dict():
    assert payload_source({"policy": {"id": "x"}, "id": "outer"}, "policy") == {"id": "x"}


def test_canonical_json_sorts_keys():
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_canonical_json_matches_existing_fingerprint_and_generation_serialization():
    details = {"b": 1, "a": ["z", "y"]}
    expected = json.dumps(details, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    diagnostic = TemplateDiagnostic(code="x", message="y", details=details)

    assert canonical_json(details) == expected
    assert diagnostic.fingerprint()[-1] == expected

    payload = {
        "roots": ["/tmp/templates"],
        "schema_version": 1,
        "files": [{"path": "template.json", "sha256": "abc"}],
    }
    old_generation = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
            "utf-8"
        )
    ).hexdigest()
    new_generation = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

    assert new_generation == old_generation
