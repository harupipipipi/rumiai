from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from tobkiri_protocol.validation import validate_document

ROOT = Path(__file__).resolve().parent.parent


def _command(request_id: str, command: str, **overrides: Any) -> dict[str, Any]:
    request: dict[str, Any] = {
        "protocol": "io.tobkiri.cli.io.v1",
        "type": "command",
        "request_id": request_id,
        "command": command,
        "arguments": {},
        "stdin": None,
        "tty": False,
        "output_limit": 1_048_576,
    }
    request.update(overrides)
    return request


def _run_cli(requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        item for item in [str(ROOT), environment.get("PYTHONPATH", "")] if item
    )
    completed = subprocess.run(
        [sys.executable, "-m", "tobkiri.cli_shell", "--structured-stdio"],
        cwd=ROOT,
        env=environment,
        input="".join(json.dumps(request) + "\n" for request in requests),
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    return [validate_document(line, "cli_io") for line in completed.stdout.splitlines()]


def test_actual_cli_shell_structured_protocol_resolves_profiles_and_identity() -> None:
    requests = [
        _command("cli:req:identity001", "profile.identity", profile_id=profile_id)
        for profile_id in (
            "defaults-modern",
            "defaults-modern-electron",
            "defaults-modern-cli",
        )
    ]
    responses = _run_cli(requests)
    identities = [json.loads(response["stdout"]) for response in responses]

    assert [item["shell_provider_id"] for item in identities] == [
        "shell.tauri.default",
        "shell.electron.default",
        "shell.cli.default",
    ]
    assert {tuple(item["backend_provider_ids"]) for item in identities} == {("defaultspack",)}
    assert {tuple(item["state_owners"]) for item in identities} == {
        (
            "defaultspack.conversation",
            "defaultspack.agent",
            "defaultspack.tool_catalog",
            "defaultspack.local_settings",
        )
    }
    assert {json.dumps(item["authority_identity"], sort_keys=True) for item in identities} == {
        json.dumps(
            {
                "backend_provider_ids": ["defaultspack"],
                "state_owners": [
                    "defaultspack.conversation",
                    "defaultspack.agent",
                    "defaultspack.tool_catalog",
                    "defaultspack.local_settings",
                ],
                "profile_may_mint_host_authority": False,
            },
            sort_keys=True,
        )
    }


def test_actual_cli_shell_rejects_arbitrary_commands_and_keeps_artifacts_non_executable() -> None:
    responses = _run_cli(
        [
            _command("cli:req:health001", "health"),
            _command("cli:req:arbitrary1", "cargo tauri dev"),
            _command(
                "cli:req:limit001",
                "echo",
                stdin="x" * 32,
                output_limit=4,
            ),
        ]
    )
    assert responses[0]["type"] == "result"
    assert responses[0]["exit_status"] == 0
    assert responses[1]["type"] == "error"
    assert "command" in responses[1]["error"]
    assert responses[2]["type"] == "error"
    assert "output" in responses[2]["error"]
