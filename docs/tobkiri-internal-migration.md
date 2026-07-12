# Tobkiri internal migration

| Legacy name | Canonical name | Read support | Write behavior | Removal condition |
| --- | --- | --- | --- | --- |
| `rumi_ai` CLI | `tobkiri` CLI | Supported | New docs use `python -m tobkiri` | After a published compatibility window |
| `rumi-theme` | `tobkiri-theme` | Legacy value migrates when canonical is absent | Canonical key is written; legacy key is retained | After stored-preference migration support ends |
| `rumi-color-mode` | `tobkiri-color-mode` | Legacy value migrates when canonical is absent | Canonical key is written; legacy key is retained | After stored-preference migration support ends |
| `RUMI_*` | `TOBKIRI_*` | Not changed in this increment | Existing security-sensitive variables remain legacy contracts | Dedicated audited env migration |

This phase deliberately leaves filesystem paths, bundle identifiers, approval paths,
and capability contracts unchanged until their migrations have dedicated safety tests.
