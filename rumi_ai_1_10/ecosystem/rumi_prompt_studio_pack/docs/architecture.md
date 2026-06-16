# Architecture

`rumi_prompt_studio_pack` is declarative. It ships catalogs, schemas, policies, templates, examples, prompts, profiles, presets, local fixtures, and prompt version ledger entries. It registers no tools and grants no broad permissions.

Owned surfaces: prompt_artifact_catalog, prompt_lint_rubric, custom_instruction_migration, fixture_dry_run_contract, prompt_version_ledger.

Non-owned surfaces: model benchmarking, model routing, persistent memory storage, tool/API creation, runtime execution, and code edits.
