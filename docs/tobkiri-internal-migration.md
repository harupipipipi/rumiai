# Tobkiri internal migration

| Legacy name | Canonical name | Read support | Write behavior | Removal condition |
| --- | --- | --- | --- | --- |
| `rumi_ai` CLI | `tobkiri` CLI | Supported through the 1.x release line | Active callers use `python -m tobkiri`; the alias delegates to the same main function without a stdout warning | At the first 2.0-or-later release after a repository audit finds no active caller |
| `rumi-theme` | `tobkiri-theme` | Legacy value migrates when canonical is absent | Canonical key is written; legacy key is retained | After stored-preference migration support ends |
| `rumi-color-mode` | `tobkiri-color-mode` | Legacy value migrates when canonical is absent | Canonical key is written; legacy key is retained | After stored-preference migration support ends |
| `RUMI_API_TOKEN` | `TOBKIRI_API_TOKEN` | Canonical first, legacy fallback | Canonical for new integrations | After the compatibility window |
| `RUMI_USER_DATA` | `TOBKIRI_USER_DATA` | Canonical first, legacy fallback | Canonical for new integrations | After app-data migration adoption |
| `RUMI_LOG_LEVEL` | `TOBKIRI_LOG_LEVEL` | Canonical first, legacy fallback | Canonical for new integrations | After the compatibility window |
| `RUMI_LOG_FORMAT` | `TOBKIRI_LOG_FORMAT` | Canonical first, legacy fallback | Canonical for new integrations | After the compatibility window |

This phase deliberately leaves filesystem paths, bundle identifiers, approval paths,
and capability contracts unchanged until their migrations have dedicated safety tests.

## CLI compatibility window

`python -m tobkiri` is the only canonical command for documentation, launchers,
CI, smoke tests, and new integrations. `python -m rumi_ai` remains available for
the full Tobkiri 1.x release line so existing automation is not broken by a minor
upgrade. It intentionally emits no deprecation warning because machine-readable
commands such as `--health` must keep stdout and stderr stable.

The root shim may be removed in a separate PR for the first 2.0-or-later release
only after a repository-wide caller audit classifies every remaining `rumi_ai`
reference as compatibility code, migration history, or a separately tracked
persistence identifier. Removal is not part of the current migration phase.
