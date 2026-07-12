# Migration

This document summarizes the compatibility path from legacy defaults to defaultspack v2.

- `user.csv` data should be migrated to `user.json`.
- Legacy module imports should use the new backend/frontend loader entry points.
- Existing runtime behavior is preserved through thin compatibility layers.
