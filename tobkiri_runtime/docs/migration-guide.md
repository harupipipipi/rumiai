# Migration Guide

## Summary

Move legacy defaults workflows to defaultspack v2 with minimal disruption.

## Notes

- Preserve existing file-backed data where possible.
- Use the new loaders instead of direct module traversal.
- Prefer compatibility shims over broad refactors.
