# Rumi AI

Rumi AI is a modular AI runtime and tooling workspace.

The repository keeps the runtime implementation under `rumi_ai_1_10/`, while `rumi_ai/` provides a version-stable Python entrypoint.

## Repository Layout

- `rumi_ai_1_10/`: current kernel/runtime source tree
- `rumi_ai/`: version-stable Python entrypoint package
- `pack-shell/`: desktop pack launcher
- `rumi_viewer/`: viewer application

## Start

```bash
python -m rumi_ai --health
python -m rumi_ai
```

## Development

```bash
cd rumi_ai_1_10
python -m pytest tests/test_capability_trust_store.py
```

## Quality Pack

継続開発・監査・回帰確認の運用パックは以下を参照:

- `rumi_ai_1_10/docs/quality_pack/philosophy_memo.md`
- `rumi_ai_1_10/docs/quality_pack/claude_desktop_quality_pack.md`
- `rumi_ai_1_10/docs/quality_pack/test_coverage_matrix.md`
- `rumi_ai_1_10/docs/quality_pack/api_route_coverage_matrix.yaml`
- `rumi_ai_1_10/docs/quality_pack/frontend_ux_contract_matrix.yaml`
- `rumi_ai_1_10/docs/quality_pack/viewer_release_contract_matrix.yaml`
- `rumi_ai_1_10/docs/quality_pack/longrun_migration_contract_matrix.yaml`
- `rumi_ai_1_10/docs/quality_pack/security_permission_contract_matrix.yaml`
- `rumi_ai_1_10/docs/quality_pack/ui_viewer_recovery_contract_matrix.yaml`
- `rumi_ai_1_10/docs/quality_pack/runtime_boundary_contract_matrix.yaml`
- `rumi_ai_1_10/docs/quality_pack/philosophy_re_evaluation_log.md`
- `rumi_ai_1_10/docs/quality_pack/debug_playbook.md`
- `rumi_ai_1_10/docs/quality_pack/manual_regression_scenarios*.yaml`
- `rumi_ai_1_10/scripts/quality_pack/run_claude_quality_pack.sh`
- `rumi_ai_1_10/scripts/quality_pack/run_debug_bundle.sh`

## HMAC Migration

```bash
python -m rumi_ai migrate-hmac
```

## Components

- `rumi_ai`: stable CLI and module entrypoint
- `rumi_ai_1_10`: kernel, runtime, frontend, and docs
- `pack-shell`: launches desktop packs and brokers token/bootstrap flow
- `rumi_viewer`: viewer-side application shell

For architecture and runtime details, see [rumi_ai_1_10/README.md](./rumi_ai_1_10/README.md).
