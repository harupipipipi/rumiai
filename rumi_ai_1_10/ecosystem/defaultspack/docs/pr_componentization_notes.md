<!-- docs-i18n-links:start -->
[EN](./pr_componentization_notes.md) | [JP](./i18n/ja/pr_componentization_notes.md) | [KR](./i18n/ko/pr_componentization_notes.md) | [CN](./i18n/zh-cn/pr_componentization_notes.md)
<!-- docs-i18n-links:end -->

# PR Notes: Defaultspack Componentization

## Summary

This PR moves defaultspack toward extension-like component folders while preserving existing public behavior. Component manifests now cover webhook defaults, external profiles, integrations, gateway channels, URL providers, tools, providers, prompts, routes, and UI surfaces.

## Architecture Goal

Adding a surface should become a file-drop workflow:

```text
domain/<category>/<component_id>/manifest.json
```

Central registries remain compatibility and discovery layers. They should not regain hardcoded connector/profile/provider/tool/prompt defaults.

## New Component Folder Convention

New domain surfaces should be added as file-drop components:

```text
domain/<category>/<component_id>/
  manifest.json
  rules.py or rules.json
  handler.py / adapter.py / inbound.py / output.py
  README.md optional
  tests optional
```

The manifest is the discovery contract. It carries ids, category/kind, version/status, entrypoints, routes, profiles, security, UI, policy, capabilities, aliases, compatibility metadata, conversion targets, and source pack ownership where useful.

## PR #92 Compatibility

- Gitlawb OpenGateway provider id remains `gitlawb-opengateway`.
- Gitlawb OpenGateway model ids remain:
  - `gitlawb-opengateway/mimo-v2.5-pro`
  - `gitlawb-opengateway/mimo-v2-flash`
  - `gitlawb-opengateway/mimo-v2-omni`
- No-key behavior, default base URL behavior, browser User-Agent behavior, and fixed model allowlist behavior are preserved.
- MiMo Omni keeps verified image metadata.
- `rumi_model_catalog_pack` provider/model manifests are preserved and remain manifest-backed.
- LINE Biz webhook acknowledgement/background processing is preserved, including acknowledgement text, reply token reuse suppression, current-turn chat history mode, physical click prompt behavior, origin/source recording, signature verification, and audience policy behavior.
- Browser/computer driver safety remains preserved in `rumi_default_tools_pack`, including visible-screen-only behavior, foreground guards, approval-required physical actions, URL scheme restrictions, and fallback order.

## What Changed By Phase

1. Documented the domain component folder convention.
2. Added shared manifest discovery, validation, registry, aliases, diagnostics, and multi-pack roots.
3. Moved webhook endpoint/security defaults into component manifests.
4. Moved input profiles, output profiles, and audience policies into component-backed manifests.
5. Split LINE, Discord, and Slack integrations behind component entrypoints while keeping block shims.
6. Componentized gateway channels and webhook URL providers with legacy import shims.
7. Added manifest-backed tool/browser/computer component metadata, including `rumi_default_tools_pack`.
8. Moved provider/model metadata into provider components, including Gitlawb OpenGateway.
9. Componentized prompt and template surfaces.
10. Loaded route and UI surface metadata from component manifests.
11. Added guardrail and compatibility tests to prevent re-centralizing component defaults.
12. Added migration docs, PR notes, and final quality checks.

## Compatibility Guarantees

- Existing endpoint ids remain stable: `line-main`, `discord-main`, `slack-main`, `test-webhook`.
- Existing profile ids remain stable: `line.default`, `discord.default`, `slack.default`, `generic.webhook.default`.
- Existing provider aliases, route paths, tool ids, prompt ids, and old import paths remain available through compatibility layers.
- Component discovery fails soft on bad manifests and reports diagnostics instead of executing arbitrary code.
- Approval and security behavior stays in the existing policy/executor paths.

## Existing Ids And Routes Preserved

- Endpoint ids remain `line-main`, `discord-main`, `slack-main`, and `test-webhook`.
- Profile ids remain `line.default`, `discord.default`, `slack.default`, and `generic.webhook.default`.
- Public webhook, setup, UI, provider, prompt, and tool route paths remain backed by the existing route table, with manifest-backed routes added as metadata/discovery rather than replacing public paths.
- Provider aliases, tool ids, prompt ids, endpoint ids, and old block/import paths are preserved through compatibility shims.

## Tests Run

- `python -m pytest rumi_ai_1_10/tests/test_defaultspack_webhook_endpoints.py rumi_ai_1_10/tests/test_defaultspack_external_send_tool.py rumi_ai_1_10/tests/test_defaultspack_tool_policy.py rumi_ai_1_10/tests/test_defaultspack_ui_registry.py rumi_ai_1_10/tests/test_defaultspack_mcp_registry.py rumi_ai_1_10/tests/test_defaultspack_agent_service_plan.py rumi_ai_1_10/tests/test_defaultspack_opengateway_provider.py rumi_ai_1_10/tests/test_defaultspack_google_provider.py rumi_ai_1_10/tests/test_defaultspack_line_origin_regression.py rumi_ai_1_10/tests/test_browser_cdp_driver.py rumi_ai_1_10/tests/test_browser_computer_security_windows.py rumi_ai_1_10/tests/test_computer_fallback_order.py rumi_ai_1_10/tests/test_defaultspack_domain_components.py rumi_ai_1_10/tests/test_defaultspack_external_components.py rumi_ai_1_10/tests/test_defaultspack_integration_components.py rumi_ai_1_10/tests/test_defaultspack_gateway_url_components.py rumi_ai_1_10/tests/test_defaultspack_tool_components.py rumi_ai_1_10/tests/test_defaultspack_provider_components.py rumi_ai_1_10/tests/test_defaultspack_prompt_components.py rumi_ai_1_10/tests/test_defaultspack_route_ui_components.py rumi_ai_1_10/tests/test_defaultspack_component_guardrails.py -q`: 373 passed.
- `python -m compileall rumi_ai_1_10/ecosystem/defaultspack`: passed.
- `python .github/scripts/quality_gate_nonregression.py --base-ref origin/master`: passed, with Ruff unchanged and mypy debt reduced.
- `python -m pytest rumi_ai_1_10/tests -q`: 4339 passed, 20 skipped.

## Known Risks

- The PR intentionally keeps compatibility shims, so some fallback tables remain until downstream imports and call sites are migrated.
- Component metadata and legacy registries coexist; future cleanup should retire duplicated fallback declarations only after coverage is broader.
- Discovery now spans multiple ecosystem packs, so malformed third-party manifests can surface diagnostics even when runtime behavior continues.

## Rollback Notes

Each phase is a coherent commit. If needed, revert the relevant phase commit while retaining later docs/tests as guidance. The compatibility shims make rollback localized because old imports and route paths still exist.

## Follow-Up Cleanup

- Continue moving legacy fallback tables into manifests as coverage grows.
- Expand component manifests for remaining provider/catalog metadata.
- Add richer UI for route/component diagnostics.
- Gradually retire compatibility shims only after downstream imports are migrated.
