# Interfaces

    The primary interface is a set of strict schemas under `schemas/` plus handoff policies under `policies/`.

`defaultspack` remains the setup, grant, and review authority. This pack only prepares migration contracts and downstream handoff packets.

No executable code is included, and network is none by default.

    ## Owner Surfaces

    - `repo_inventory`
- `migration_plan`
- `codemod_plan`
- `pr_shard_plan`
- `compatibility_matrix`
- `risk_ledger`
- `test_gate_plan`
- `rollback_plan`
- `migration_handoff_packet`

    ## Adjacent Owner Handoffs

    - `cli_ide_execution` -> `handoff_to_rumi_code_ide_pack`
- `file_editing_patch_execution` -> `handoff_to_rumi_code_ide_pack`
- `subagent_pr_execution` -> `handoff_to_rumi_subagent_pr_manager_pack`
- `release_deploy_runbooks` -> `handoff_to_rumi_devops_release_pack`
- `security_findings` -> `handoff_to_rumi_security_review_pack`
- `model_scoring` -> `handoff_to_rumi_model_evals_pack`
- `runtime_telemetry` -> `handoff_to_rumi_observability_pack`
- `migration_planning_contract` -> `owned_by_rumi_code_migration_pack`
- `tool_aliases` -> `prefer_explicit_pack_namespace`
