# Rumi Schedule Review

Review a workflow scheduler contract for safety and ownership.

Check:

- Schedule kind and cadence are clear.
- Owner route is explicit and available.
- Evidence is named and local or owner-provided.
- Stop conditions are present.
- Retry policy has bounded attempts.
- Delivery handoff has an audience policy when external delivery is involved.
- Overlap with defaultspack, agent services, connector gateway, and release packs is contract-only.

Do not approve, install, or execute automations. Do not override owner-pack grants or defaultspack approvals. If a contract lacks owner route, evidence, or stop conditions, recommend blocking it until those fields are supplied.
