#!/usr/bin/env python3
"""Minimal authenticated-channel endpoint for the managed PackVM guest."""

from __future__ import annotations

import hashlib
import json
import sys


PROTOCOL = "io.tobkiri.packvm-supervisor.v1"
BUILD_ID = "tobkiri-packvm-runner-1"


def main() -> int:
    """Serve one bounded request from stdin and emit one JSON response."""
    try:
        request = json.loads(sys.stdin.read(1024 * 1024 + 1))
        if not isinstance(request, dict):
            raise ValueError("request must be an object")
        operation = request.get("operation")
        if operation == "doctor":
            response = {
                "ok": True,
                "protocol": PROTOCOL,
                "build_id": BUILD_ID,
            }
        elif (
            operation == "invoke"
            and request.get("contract_id") == "io.tobkiri.packvm.attestation.v1"
            and request.get("operation_id") == "challenge"
            and isinstance(request.get("payload"), dict)
            and isinstance(request["payload"].get("challenge"), str)
            and len(request["payload"]["challenge"]) == 64
        ):
            challenge = request["payload"]["challenge"]
            response = {
                "ok": True,
                "protocol": PROTOCOL,
                "payload": {
                    "challenge_digest": "sha256:"
                    + hashlib.sha256(challenge.encode()).hexdigest()
                },
            }
        else:
            # Artifact materialization is deliberately a separate Host contract.
            # Never substitute an in-process Python executor here.
            response = {
                "ok": False,
                "error": "artifact_not_materialized",
                "protocol": PROTOCOL,
            }
    except (ValueError, json.JSONDecodeError) as exc:
        response = {"ok": False, "error": "invalid_request", "message": str(exc)}
    sys.stdout.write(json.dumps(response, sort_keys=True, separators=(",", ":")))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
