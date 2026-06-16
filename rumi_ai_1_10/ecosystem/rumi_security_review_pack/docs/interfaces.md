# Interfaces

## Flows, Functions, Handlers, Routes, Events, Stores

This pack declares no pack-owned flows, modifiers, functions, handlers, HTTP routes, runtime events, stores, or executable tools.

## Catalogs

- `catalog/review_controls.yaml`: control families for threat modeling, secret scanning, grants, MCP/browser review, dependency review, and release signoff.
- `catalog/risk_taxonomy.yaml`: risk categories, severity defaults, evidence expectations, and escalation cues.
- `catalog/finding_schema.json`: JSON schema for local security finding records.

## Profiles

- `rumi_security_review.security_reviewer`: local-first reviewer profile for pack and release review.

## Prompts

- `prompts/security_reviewer.system.md`: system prompt for Rumi-native security review.
- `prompts/release_signoff.system.md`: system prompt for release security signoff.

## Presets

- `presets/threat_model_review.preset.yaml`: structured threat model review.
- `presets/permission_grant_review.preset.yaml`: grants, approvals, and capability review.
- `presets/mcp_browser_risk_review.preset.yaml`: MCP and browser risk review.
- `presets/dependency_release_signoff.preset.yaml`: dependency and release readiness review.

## Examples

- `examples/pack_security_review.example.yaml`: example local review record.
- `examples/release_signoff.example.yaml`: example signoff record.

## Required Secrets

None.

This pack must not embed secrets, access tokens, API keys, OAuth material, bearer credentials, passwords, private keys, or remote scanning service configuration.

## Network

No network access is required by this pack. Dependency or vulnerability information can be recorded from user-provided local evidence. Any future network-backed scanner belongs in a different executable pack and must request its own grants and approvals.

## Grants

This pack does not request or mutate grants. It may recommend that a reviewer inspect grants or approvals, but it must not override defaultspack decisions.

## Overlap Behavior

- With `defaultspack`: this pack reviews permission grants, approvals, tool manifests, and release readiness. It does not override, approve, deny, or rewrite grants.
- With MCP gateway packs: this pack reviews server risk, namespace clarity, requested scopes, and approval evidence. It does not connect or route MCP servers.
- With browser packs: this pack reviews browser permissions, page access, automation risk, and data exposure. It does not operate browser sessions.
- With dependency tooling: this pack records review outcomes from local evidence. It does not fetch package metadata or vulnerability feeds.

When overlap exists, prefer the owning pack for enforcement and use this pack only for review evidence and signoff guidance.
