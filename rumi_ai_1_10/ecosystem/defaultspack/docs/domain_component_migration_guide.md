<!-- docs-i18n-links:start -->
[EN](./domain_component_migration_guide.md) | [JP](./i18n/ja/domain_component_migration_guide.md) | [KR](./i18n/ko/domain_component_migration_guide.md) | [CN](./i18n/zh-cn/domain_component_migration_guide.md)
<!-- docs-i18n-links:end -->

# Defaultspack Domain Component Migration Guide

This guide explains how to add or migrate domain surfaces without growing central registries.

## Compatibility First

Do not rename public ids, routes, or imports during migration. Keep the old import path as a shim when code moves into a component folder. Keep existing route paths, endpoint ids, profile ids, prompt ids, provider aliases, and tool ids stable.

## Adding A Webhook Or Integration

Create:

```text
domain/webhooks/<provider>/manifest.json
domain/integrations/<provider>/manifest.json
domain/integrations/<provider>/inbound.py
domain/integrations/<provider>/security.py
domain/integrations/<provider>/normalizer.py
domain/integrations/<provider>/output.py
domain/integrations/<provider>/rules.json
```

Declare endpoint defaults in `domain/webhooks/<provider>/manifest.json`. Put runtime behavior and route metadata in `domain/integrations/<provider>/manifest.json`. Leave `blocks/integrations/<provider>.py` as a shim.

## Adding A Provider Or Model

Create:

```text
domain/providers/<provider_id>/manifest.json
domain/providers/<provider_id>/models.json
```

Provider components augment runtime metadata. Manifest-backed catalog packs, such as `rumi_model_catalog_pack`, remain separate and continue to own provider/model catalog manifests. Provider adapters must not import tool registry or tool policy modules.

## Adding A Tool

Create:

```text
domain/tools/<tool_id>/manifest.json
```

The component manifest can point to an existing `tools/<tool_id>/manifest.json` with `entrypoints.tool_manifest`. Approval and execution must still flow through `ToolRegistry`, `ToolOrchestrator`, `ToolExecutor`, and existing policy checks.

## Adding A Browser Or Computer Driver Surface

Create component metadata under the owning pack, for example:

```text
rumi_default_tools_pack/domain/browser/<driver_id>/manifest.json
rumi_default_tools_pack/domain/computer/<driver_id>/manifest.json
```

Preserve visible-screen-only behavior, foreground guards, explicit physical-action approval, and existing fallback order.

## Adding A Prompt Or Template

Create:

```text
domain/prompts/<prompt_id>/manifest.json
domain/prompts/<prompt_id>/prompt.md
domain/prompts/<prompt_id>/rules.json
domain/templates/<template_id>/manifest.json
```

Prompt components are provider/tool independent. User-saved prompts still live in `user_data/shared/prompts`.

## Adding Routes Or UI Metadata

Components may declare route records in `routes`. Existing route tables remain fallback compatibility. UI surfaces live under:

```text
domain/ui_surfaces/<surface_id>/manifest.json
```

Expose UI metadata through `ui` in the manifest and keep the frontend catalog shape stable.

## Review Checklist

- Component manifest validates with no diagnostics.
- Old import path still imports.
- Old ids and routes still resolve.
- Tests cover moved defaults and shims.
- Security defaults did not weaken.
- Central registries load or discover components instead of owning new defaults.
