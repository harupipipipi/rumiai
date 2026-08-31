#!/usr/bin/env python3
"""Verify the one-time reviewed Pack architecture baseline bootstrap."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


EXPECTED_REFERENCE_SHA256 = (
    "9a10c35337e97b5a1b554fe732b63de870877434a1963121e5efb1ca1304f40d"
)
EXPECTED_EXCEPTION_COUNT = 110


def _load_baseline(path: Path) -> tuple[bytes, dict[str, Any]]:
    payload = path.read_bytes()
    document = json.loads(payload)
    if not isinstance(document, dict) or set(document) != {
        "schema_version",
        "policy",
        "exceptions",
    }:
        raise ValueError("Pack architecture bootstrap schema is invalid")
    if document["schema_version"] != 2:
        raise ValueError("Pack architecture bootstrap schema version is invalid")
    if document["policy"] != "shrink_only_exact_edges":
        raise ValueError("Pack architecture bootstrap policy is invalid")
    exceptions = document["exceptions"]
    if not isinstance(exceptions, list) or len(exceptions) != EXPECTED_EXCEPTION_COUNT:
        raise ValueError("Pack architecture bootstrap exception count is invalid")
    identities = [
        exception.get("identity") if isinstance(exception, dict) else None
        for exception in exceptions
    ]
    if any(not isinstance(identity, str) or not identity for identity in identities):
        raise ValueError("Pack architecture bootstrap identity is invalid")
    if len(set(identities)) != len(identities):
        raise ValueError("Pack architecture bootstrap identities are not unique")
    return payload, document


def verify_bootstrap(candidate: Path, reference: Path) -> None:
    """Require a distinct immutable reference and an exact candidate match."""
    candidate_stat = candidate.stat()
    reference_stat = reference.stat()
    if candidate.resolve() == reference.resolve() or (
        candidate_stat.st_dev,
        candidate_stat.st_ino,
    ) == (reference_stat.st_dev, reference_stat.st_ino):
        raise ValueError("candidate cannot authorize its own bootstrap baseline")
    reference_payload, _ = _load_baseline(reference)
    if hashlib.sha256(reference_payload).hexdigest() != EXPECTED_REFERENCE_SHA256:
        raise ValueError("Pack architecture bootstrap reference digest mismatch")
    candidate_payload, _ = _load_baseline(candidate)
    if candidate_payload != reference_payload:
        raise ValueError("Pack architecture bootstrap candidate is not exact")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        verify_bootstrap(arguments.candidate, arguments.reference)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
