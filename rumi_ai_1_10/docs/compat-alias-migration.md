# Compatibility Alias Migration

Last updated: 2026-07-10

`defaultspack.*` is the canonical function vocabulary. `defaults.*` names are
compatibility aliases and must not be used by new callers.

## Authoritative Inventory

`ecosystem/defaultspack/compat_aliases.yaml` is the explicit, machine-checked
allowlist and canonical replacement index. Every remaining alias is a key under
`aliases`; its adjacent `replacement` value is the canonical name callers must
adopt. Each entry also declares an owner, migration note (`reason`), and removal
deadline. The integrity scan fails for an alias that is absent from this index,
lacks a migration note, or points to a canonical alias on another function.
The generated human-readable list of every alias and replacement is
`docs/defaultspack-compat-alias-reference.md`; CI also checks that it matches the
allowlist exactly.

No request arguments, user identifiers, prompt text, file paths, URLs, tokens,
or other payload values are recorded by compatibility telemetry. Audit events
contain only the alias, canonical replacement, migration stage, caller class
(`internal` or `external`), schema version, and whether a warning was emitted.

## Stages

1. **Inventory:** complete. Existing aliases and replacements are captured in
   the allowlist; new aliases require ownership and migration metadata.
2. **Warning:** active. Actual alias resolution writes a local audit event.
   Non-internal callers receive one structured deprecation warning per alias and
   process. Internal callers are measured without warning noise.
3. **Enforcement:** planned for v2.4. Tests and integrity scans already reject
   unallowlisted aliases; runtime enforcement will advance per alias after usage
   evidence confirms callers have migrated.
4. **Removal:** staged by each entry's `remove_after`. Removed aliases disappear
   from both function manifests and the allowlist while canonical names remain.

## First Removal

The `defaults.model_runtime.*` compatibility group was removed after repository
search found no callers outside generated manifests and the compatibility
inventory. The canonical `defaultspack.ai.*` and
`defaultspack.model_runtime.*` aliases remain supported.

Run the guard locally with:

```bash
cd rumi_ai_1_10
python scripts/quality/scan_defaultspack_integrity.py
```
