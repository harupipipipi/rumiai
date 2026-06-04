# Interfaces

    ## Inputs

    - Local artifacts supplied by the user or by an adjacent owner pack.
    - Schema-bound records listed in `ecosystem.json`.
    - Evidence IDs, source spans, and explicit uncertainty notes.

    ## Outputs

    - Evidence-linked drafts.
    - Review checklist results.
    - Handoff packets with owner pack, reason, and artifact path.
    - Decision records with explicit `result_claim` and `analysis_boundary` fields.

    ## Decision Claim Boundary

    Design-only records must set `result_claim.status` to `not_claimed`. Claims about winners, significance, lift, or metric movement require supplied result artifacts and must not come from queries executed by this pack.

    ## Handoff Owners

    - `rumi_data_analysis_pack`: Run analytics queries and statistical result calculations outside this pack.
- `rumi_observability_pack`: Collect runtime telemetry and dashboards outside this pack.
- `rumi_devops_release_pack`: Own production rollout, feature flags, and rollback execution.
- `rumi_model_evals_pack`: Run model benchmarks when the experiment concerns model behavior.
- `rumi_business_ops_pack`: Business decisions and operating workflows remain separate from design.

    ## Required Secrets

    None.

    ## Does Not Provide

    - analytics query execution
- production rollout
- runtime telemetry collection
- model benchmark execution
- business decision execution
- feature flag mutation
