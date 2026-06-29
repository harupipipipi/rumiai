# Settings Contribution Rules

These rules prevent Settings from becoming a junk drawer with ambitions.

## Mandatory metadata

Every Settings contribution must include:

```json
{
  "id": "pack.panel.id",
  "owner": "pack_id_or_core",
  "title": { "en": "Display name", "ja": "表示名" },
  "description": { "en": "What this setting does." },
  "section": "models_api",
  "priority": 50,
  "frequency": "weekly",
  "audience": "normal",
  "risk": "none",
  "component": "settings/component.tsx"
}
```

## Section ownership

- OAuth/API keys/accounts -> `accounts_connections`
- Tool enable/disable/permissions -> `tools_mcp`
- Screen/click/type/browser/cloud continuation -> `computer_automation`
- Theme/layout/gradients -> `workspace_ui`
- Pack lifecycle -> `packs_extensions`
- Raw JSON/debug -> `diagnostics`

## UI label rules

- `title` must be human-readable.
- `title` must not equal `id`, `provider_id`, `module_id`, or `component` path.
- Internal id can be shown only in Advanced details.
- Lowercase raw codename labels such as `mimo` are blocked in normal UI.

## Priority rules

- `0-19`: core setup blockers only.
- `20-49`: high-priority normal user settings.
- `50-79`: common settings.
- `80-119`: rare/power-user settings.
- `120+`: advanced/diagnostic.

Packs may not contribute into `0-19` unless core explicitly whitelists the contribution.

## Visibility rules

Normal users see:

- daily
- weekly
- missing required configuration

Power users can opt into rare settings.
Developer/debug settings live under Advanced/Diagnostics.

## Review checklist

- Does the setting answer a user question?
- Is it in the correct section by user intent?
- Does it have clear status and next action?
- Does it expose risk before action?
- Does it work under profiles?
- Does it have a migration path?
- Does a test prevent this from regressing?
