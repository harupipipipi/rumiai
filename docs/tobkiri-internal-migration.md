# Tobkiri internal migration

| Legacy name | Canonical name | Read support | Write behavior | Removal condition |
| --- | --- | --- | --- | --- |
| `rumi_ai` CLI | `tobkiri` CLI | Supported | New docs use `python -m tobkiri` | After a published compatibility window |
| `rumi-theme` | `tobkiri-theme` | Legacy value migrates when canonical is absent | Canonical key is written; legacy key is retained | After stored-preference migration support ends |
| `rumi-color-mode` | `tobkiri-color-mode` | Legacy value migrates when canonical is absent | Canonical key is written; legacy key is retained | After stored-preference migration support ends |
| `RUMI_API_TOKEN` | `TOBKIRI_API_TOKEN` | Canonical first, legacy fallback | Canonical for new integrations | After the compatibility window |
| `RUMI_USER_DATA` | `TOBKIRI_USER_DATA` | Canonical first, legacy fallback | Canonical for new integrations | After app-data migration adoption |
| `RUMI_LOG_LEVEL` | `TOBKIRI_LOG_LEVEL` | Canonical first, legacy fallback | Canonical for new integrations | After the compatibility window |
| `RUMI_LOG_FORMAT` | `TOBKIRI_LOG_FORMAT` | Canonical first, legacy fallback | Canonical for new integrations | After the compatibility window |

This phase deliberately leaves filesystem paths, bundle identifiers, approval paths,
and capability contracts unchanged until their migrations have dedicated safety tests.
