# Changelog: defaultspack v2

## Added

- Tracked `ecosystem/defaultspack` pack with canonical API route definitions
- `setup_pack` discovery and defaultspack-specific all-OK permission gating
- Function-first defaultspack operation surface
- Module catalog, persisted module state, dependency degradation, and recovery events
- Legacy `user.csv` to `user.json` migration helper

## Operational notes

- `all OK` is intentionally restricted to the `defaultspack` setup pack.
- Setup-pack install and all-OK permission operations are audit logged.
