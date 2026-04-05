# Migration Guide: Old Defaults to defaultspack v2

## Overview

This document describes how to migrate from the old `rumiai_defaults` structure
to the new `ecosystem/defaultspack/` architecture within `rumiai`.

## What Changed

### Architecture
| Old (rumiai_defaults)                | New (defaultspack v2)                          |
|--------------------------------------|------------------------------------------------|
| `blocks/` with direct import         | `functions/` with registry-based dispatch      |
| `domain/` monolithic services        | `backend/` modular managers                    |
| `transport/http.py` with block calls | Loader-based API through EcosystemLoader       |
| `static/shell.html` hardcoded UI     | `frontend/` modular component system           |
| No module health tracking            | Full state machine per module                  |
| No dependency resolution             | Topological sort with failure containment      |

### Data Format Changes
| Old Format            | New Format            | Migration Tool                     |
|-----------------------|-----------------------|------------------------------------|
| `userdata/user.csv`   | `userdata/user.json`  | `MigrationManager.migrate_user_csv_to_json()` |
| Old config JSON       | Versioned config JSON | `MigrationManager.migrate_old_config()`       |

## Migration Steps

### 1. Install defaultspack
```python
from ecosystem.defaultspack.setup_pack import SetupPackManager
mgr = SetupPackManager()
result = mgr.install_pack("defaultspack")
# result.permission_level == "all_ok"
```

### 2. Migrate User Data
```python
from ecosystem.defaultspack.migration import MigrationManager
migrator = MigrationManager()
migrator.migrate_user_csv_to_json("userdata/user.csv", "userdata/user.json")
```

### 3. Migrate Old Config
```python
migrator.migrate_old_config("old_config.json", "config/settings.json")
```

### 4. Check Deprecations
```python
migrator.log_deprecation("blocks.chat.send", "defaultspack.chat.ChatManager.add_message")
print(migrator.get_deprecation_log())
```

## Rollback

If migration fails, the MigrationManager supports rollback:
```python
migrator.rollback()
```

Old data files are never deleted during migration. New files are written
alongside old ones. To revert, simply remove the new files.

## Deprecation Schedule

- **v2.0**: Old `blocks/` direct import deprecated; compatibility shim available
- **v2.1**: Compatibility shim removed; old routes removed from production path
- **v3.0**: Old data formats no longer auto-detected

## Known Limitations

- MCP connections must be re-established after migration
- Plugin manifests from old format need manual conversion
- Layout configurations from old shell.html are not automatically migrated
- Custom prompts using Python extensions may need handler updates

## Risk Assessment

- **Low risk**: Data migration (CSV to JSON, config format)
- **Medium risk**: Route changes (old API paths deprecated)
- **Low risk**: Module state (new modules start disabled, enable on demand)

## Support

For issues during migration, check:
1. `MigrationManager.get_deprecation_log()` for deprecated features
2. `EcosystemLoader.get_catalog()` for module status
3. `ModuleStateManager.list_all()` for health details
