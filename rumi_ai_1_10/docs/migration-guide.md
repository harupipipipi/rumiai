# Migration Guide

> **Legacy stub**: root docs には Pack 固有 migration の本体を置かない方針です。現行の説明は [../ecosystem/defaultspack/docs/migration.md](../ecosystem/defaultspack/docs/migration.md) を参照してください。

## Summary

Move legacy defaults workflows to the pack-local `defaultspack` migration docs with minimal disruption.

## Notes

- Preserve existing file-backed data where possible.
- Use the new loaders instead of direct module traversal.
- Prefer compatibility shims over broad refactors.
