# Rumi Code Migration Pack

    `rumi_code_migration_pack` is a declarative setup pack for large codebase migration planning, codemod dry-run plans, PR shards, compatibility matrices, and rollback handoffs. It adds schemas, policies, examples, review gates, and handoff packets while leaving runtime execution to the existing owner packs.

    ## Required Secrets

    None.

    No executable code is included, and network is none by default.

    ## What It Provides

    - `repo_inventory`
- `migration_plan`
- `codemod_plan`
- `pr_shard_plan`
- `compatibility_matrix`
- `risk_ledger`
- `test_gate_plan`
- `rollback_plan`
- `migration_handoff_packet`

    ## Does Not Provide

    - CLI IDE command loops
- file editing and patch execution
- subagent assignment and PR execution
- release notes and deploy runbooks
- security findings
- model provider scoring
- runtime telemetry storage

    ## Handoff Boundaries

    - `cli_ide_execution` -> `handoff_to_rumi_code_ide_pack`
- `file_editing_patch_execution` -> `handoff_to_rumi_code_ide_pack`
- `subagent_pr_execution` -> `handoff_to_rumi_subagent_pr_manager_pack`
- `release_deploy_runbooks` -> `handoff_to_rumi_devops_release_pack`
- `security_findings` -> `handoff_to_rumi_security_review_pack`
- `model_scoring` -> `handoff_to_rumi_model_evals_pack`
- `runtime_telemetry` -> `handoff_to_rumi_observability_pack`
- `migration_planning_contract` -> `owned_by_rumi_code_migration_pack`
- `tool_aliases` -> `prefer_explicit_pack_namespace`
