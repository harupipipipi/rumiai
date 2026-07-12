# Migration Notes

## Old to new category mapping

```python
OLD_TO_NEW = {
    "model": "models_api",
    "api": "models_api",
    "provider": "models_api",
    "tools": "tools_mcp",
    "mcp": "tools_mcp",
    "computer_use": "computer_automation",
    "browser": "computer_automation",
    "theme": "workspace_ui",
    "layout": "workspace_ui",
    "pack": "packs_extensions",
    "debug": "diagnostics",
}
```

## Label cleanup

Raw labels must be converted or hidden:

```python
DISPLAY_NAME_FIXES = {
    "mimo": "Mimo model preset",
    "computer_use_gradient": "Automation visual indicator",
}
```

If a setting is obsolete, migrate it to Advanced > Legacy and mark it for deletion in the next breaking settings migration.

## Compatibility

- Keep old keys readable for one release.
- Write only new keys after migration.
- Store migration result in diagnostics.
- Allow rollback by keeping previous settings snapshot.
