# Architecture

The pack separates contract ownership from runtime ownership. `rumi_code_migration_pack` owns the reviewable contract surfaces listed in `ecosystem.json`; adjacent packs own execution, storage, rendering, telemetry, connector calls, or browser control.

## Runtime Shape

- Declarative metadata only.
- No executable code.
- No host execution.
- No bundled credentials.
- No network permission by default.
