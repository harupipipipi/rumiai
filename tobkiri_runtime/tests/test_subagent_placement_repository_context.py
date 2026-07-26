from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import pytest
from jsonschema import Draft202012Validator

from ecosystem.rumi_repository_context_pack.runtime.context import (
    AI_GENERATE,
    FILE_INSPECT,
    PLACEMENT_COMPILE,
    RepositoryContextPreparer,
    _candidate_files,
)
from ecosystem.rumi_subagent_placement_pack.runtime.compiler import (
    CATALOG,
    PLACEMENT,
    PROTOCOL,
    STAGE,
    PlacementCompileError,
    SubagentPlacementCompiler,
)
from ecosystem.defaultspack.domain.tool.security import (
    unsupported_execution_reason,
)


RUNTIME_ROOT = Path(__file__).resolve().parents[1]
ECOSYSTEM = RUNTIME_ROOT / "ecosystem"
PLACEMENT_PACK = ECOSYSTEM / "rumi_subagent_placement_pack"
CONTEXT_PACK = ECOSYSTEM / "rumi_repository_context_pack"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


class PlacementClient:
    def __init__(
        self,
        *,
        definition: Mapping[str, Any],
        placement: Mapping[str, Any],
        stage_fragment: Mapping[str, Any] | None = None,
    ) -> None:
        self.definition = dict(definition)
        self.placement = dict(placement)
        self.stage_fragment = dict(stage_fragment or {})

    def providers(self, contract_id: str) -> list[dict[str, str]]:
        providers = {
            CATALOG: [
                {
                    "provider_instance_id": "repository-context.catalog",
                    "source_pack_id": "rumi_repository_context_pack",
                }
            ],
            PLACEMENT: [
                {
                    "provider_instance_id": "repository-context.placement",
                    "source_pack_id": "rumi_repository_context_pack",
                }
            ],
            STAGE: [
                {
                    "provider_instance_id": "subagent-placement.core-stage",
                    "source_pack_id": "rumi_subagent_placement_pack",
                }
            ],
            PROTOCOL: [
                {
                    "provider_instance_id": "subagent-placement.protocols",
                    "source_pack_id": "rumi_subagent_placement_pack",
                }
            ],
        }
        return providers.get(contract_id, [])

    def invoke(
        self,
        contract_id: str,
        operation: str,
        payload: Mapping[str, Any],
        *,
        provider_instance_id: str | None = None,
    ) -> dict[str, Any]:
        del provider_instance_id
        if contract_id == PLACEMENT:
            assert operation == "get"
            return dict(self.placement)
        if contract_id == CATALOG:
            assert operation == "resolve"
            return {"matches": [dict(self.definition)]}
        if contract_id == PROTOCOL:
            assert operation == "list"
            return {
                "protocols": [
                    {
                        "id": "agent-tool",
                        "ref": "tobkiri.protocol/agent-tool/v1",
                    }
                ]
            }
        if contract_id == STAGE:
            assert operation == "compile"
            return {"plan_fragment": dict(self.stage_fragment)}
        raise AssertionError((contract_id, operation, payload))


def _compile_payload() -> dict[str, Any]:
    capabilities = [
        "ai.gateway.generate",
        "file.inspect",
        "subagent.placement.compile",
    ]
    return {
        "placement_id": "repository-context",
        "capability_plan": {
            "plan_id": "plan-test",
            "registry_revision": "registry-test",
        },
        "registry_revision": "registry-test",
        "topology_revision": "topology-test",
        "profile_policy": {"allowed_capabilities": capabilities},
        "workspace_policy": {"allowed_capabilities": capabilities},
        "host_policy": {"allowed_capabilities": capabilities},
        "task_grant": {"allowed_capabilities": capabilities},
        "host_enforcement": {
            "tool_allowlist": "host_enforced",
            "workspace_scope": "host_enforced",
            "output_schema": "host_validated",
        },
    }


def test_placement_compiles_deterministically_with_least_authority() -> None:
    definition = _json(
        CONTEXT_PACK / "subagents" / "repository-context-subagent.json"
    )
    placement = _json(
        CONTEXT_PACK / "placements" / "repository-context.placement.json"
    )
    client = PlacementClient(
        definition=definition,
        placement=placement,
        stage_fragment={"diagnostics": {"stage": "passed"}},
    )
    compiler = SubagentPlacementCompiler(client)

    first = compiler.compile(_compile_payload())
    second = compiler.compile(_compile_payload())

    assert first["plan_hash"] == second["plan_hash"]
    assert first["effective_authority"] == [
        "ai.gateway.generate",
        "file.inspect",
        "subagent.placement.compile",
    ]
    assert first["placement"]["id"] == "repository-context"
    assert first["diagnostics"]["stage"] == "passed"
    plan_schema = _json(
        ECOSYSTEM
        / "defaultspack"
        / "schemas"
        / "effective-subagent.v1.schema.json"
    )
    Draft202012Validator(plan_schema).validate(first)


def test_placement_fails_closed_for_missing_required_capability() -> None:
    definition = _json(
        CONTEXT_PACK / "subagents" / "repository-context-subagent.json"
    )
    placement = _json(
        CONTEXT_PACK / "placements" / "repository-context.placement.json"
    )
    payload = _compile_payload()
    payload["workspace_policy"] = {"allowed_capabilities": ["file.inspect"]}

    with pytest.raises(
        PlacementCompileError,
        match="required Subagent capabilities are unavailable",
    ):
        SubagentPlacementCompiler(
            PlacementClient(definition=definition, placement=placement)
        ).compile(payload)


def test_placement_stage_cannot_widen_authority() -> None:
    definition = _json(
        CONTEXT_PACK / "subagents" / "repository-context-subagent.json"
    )
    placement = _json(
        CONTEXT_PACK / "placements" / "repository-context.placement.json"
    )
    client = PlacementClient(
        definition=definition,
        placement=placement,
        stage_fragment={
            "effective_authority": [
                "ai.gateway.generate",
                "file.inspect",
                "git.publish",
                "subagent.placement.compile",
            ]
        },
    )

    with pytest.raises(PlacementCompileError, match="widened authority"):
        SubagentPlacementCompiler(client).compile(_compile_payload())


def test_candidate_filter_excludes_secrets_and_dependencies() -> None:
    items = [
        {"path": "src/repository_context.py", "size": 100, "is_file": True},
        {"path": "node_modules/library.js", "size": 100, "is_file": True},
        {"path": ".env", "size": 100, "is_file": True},
        {"path": "asset.png", "size": 100, "is_file": True},
    ]

    candidates, excluded = _candidate_files(
        items,
        "repository context",
        max_candidates=10,
        max_file_bytes=1000,
    )

    assert [item["path"] for item in candidates] == [
        "src/repository_context.py"
    ]
    reasons = {item["path"]: item["reason"] for item in excluded}
    assert reasons["node_modules/library.js"] == "generated_or_dependency_path"
    assert reasons[".env"] == "secret_like_path"
    assert reasons["asset.png"] == "non_text_extension"


class PrepareClient:
    def __init__(self) -> None:
        self.ai_calls: list[dict[str, Any]] = []
        self.files = {
            "src/auth.py": "def verify_token(token):\n    return bool(token)\n",
            "src/theme.css": ".page { color: blue; }\n",
            "config/api_key.txt": "api_key=must-not-leave-workspace\n",
        }

    def invoke(
        self,
        contract_id: str,
        operation: str,
        payload: Mapping[str, Any],
        **_: Any,
    ) -> dict[str, Any]:
        if contract_id == PLACEMENT_COMPILE:
            return {
                "placement": {"id": "repository-context"},
                "plan_hash": "sha256:effective-plan",
                "bindings": [
                    {
                        "slot": "model",
                        "provider_ref": "route://utility/context-summarizer",
                    }
                ],
                "budgets": {"maximum_tool_calls": 260},
            }
        if contract_id == FILE_INSPECT and operation == "list":
            return {
                "items": [
                    {"path": path, "size": len(content), "is_file": True}
                    for path, content in self.files.items()
                ]
            }
        if contract_id == FILE_INSPECT and operation == "read":
            return {"content": self.files[str(payload["path"])]}
        if contract_id == AI_GENERATE:
            request = dict(payload)
            self.ai_calls.append(request)
            if len(self.ai_calls) == 1:
                output = {
                    "selected_files": [
                        {
                            "path": "src/auth.py",
                            "relevance_score": 0.95,
                            "summary": "Token verification is implemented here.",
                            "evidence": ["def verify_token(token):"],
                        },
                        {
                            "path": "invented.py",
                            "relevance_score": 1,
                            "summary": "This path is invented.",
                            "evidence": ["invented"],
                        },
                    ]
                }
            else:
                output = {
                    "summary": "Authentication depends on src/auth.py.",
                    "selected_files": self.ai_calls[0]["messages"][1][
                        "content"
                    ]
                    and [
                        {
                            "path": "src/auth.py",
                            "relevance_score": 0.95,
                            "summary": "Token verification is implemented here.",
                            "evidence": ["def verify_token(token):"],
                        }
                    ],
                }
            return {
                "model_id": "opencode-zen/low-cost-test",
                "output": {"content": json.dumps(output)},
            }
        raise AssertionError((contract_id, operation, payload))


def test_repository_context_prepares_validated_evidence_bundle() -> None:
    client = PrepareClient()
    result = RepositoryContextPreparer(client).prepare(
        {
            "query": "Where is token authentication implemented?",
            "workspace_id": "workspace-test",
            "profile_id": "profile-test",
            "registry_revision": "registry-test",
            "capability_plan": {
                "plan_id": "plan-test",
                "registry_revision": "registry-test",
            },
        }
    )

    assert result["schema_version"] == "tobkiri.repository-evidence/v1"
    assert result["selected_model_ids"] == ["opencode-zen/low-cost-test"]
    assert [item["path"] for item in result["selected_files"]] == [
        "src/auth.py"
    ]
    assert result["selected_files"][0]["evidence"] == [
        "def verify_token(token):"
    ]
    assert all("api_key=" not in json.dumps(call) for call in client.ai_calls)
    excluded = {
        item["path"]: item["reason"] for item in result["excluded_files"]
    }
    assert excluded["config/api_key.txt"] == "secret_like_path"
    assert excluded["src/theme.css"] == "utility_model_not_selected"
    assert result["bundle_hash"].startswith("sha256:")


@pytest.mark.parametrize(
    ("schema_name", "document"),
    [
        (
            "subagent.v1.schema.json",
            CONTEXT_PACK / "subagents" / "repository-context-subagent.json",
        ),
        (
            "subagent-placement.v1.schema.json",
            CONTEXT_PACK / "placements" / "repository-context.placement.json",
        ),
    ],
)
def test_subagent_resources_match_their_schemas(
    schema_name: str,
    document: Path,
) -> None:
    schema = _json(ECOSYSTEM / "defaultspack" / "schemas" / schema_name)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(_json(document))


def test_tool_skill_and_activity_are_pack_native() -> None:
    tool = _json(
        CONTEXT_PACK
        / "extensions"
        / "tools"
        / "repository_context_prepare"
        / "manifest.json"
    )
    activity = _json(
        CONTEXT_PACK
        / "extensions"
        / "activities"
        / "repository_context"
        / "manifest.json"
    )
    skill = _json(
        CONTEXT_PACK
        / "extensions"
        / "skills"
        / "repository_context_preparation"
        / "manifest.json"
    )

    assert tool["execution"] == {
        "type": "global_contract",
        "contract_id": "rumi.service.repository.context.prepare.v1",
        "provider_instance_id": "repository-context.prepare",
        "operation": "prepare",
        "timeout_ms": 600000,
        "cancellable": True,
        "idempotency": "keyed",
        "retry": {"max_attempts": 1, "backoff_ms": 0},
    }
    assert tool["id"] in activity["members"]["tool_ids"]
    assert activity["id"] in skill["scope"]["activity_ids"]
    assert unsupported_execution_reason(tool) is None


@pytest.mark.parametrize("pack_root", [PLACEMENT_PACK, CONTEXT_PACK])
def test_pack_artifact_manifest_hashes_match(pack_root: Path) -> None:
    manifest = _json(pack_root / "artifact-manifest.json")

    for artifact in manifest["artifacts"]:
        content = (pack_root / artifact["path"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == artifact["sha256"]


def test_global_contract_tool_descriptor_fails_closed() -> None:
    invalid = {
        "execution": {
            "type": "global_contract",
            "contract_id": "rumi.service.example.v1",
        }
    }

    assert unsupported_execution_reason(invalid) == (
        "global_contract tools must declare execution.operation"
    )
