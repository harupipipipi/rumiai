# Overlap Policy

Connectors, Slack/Gmail/mobile clients, provider webhooks, OAuth, send/fetch APIs, push notifications, schedules, security approval tokens, and work execution are owned by adjacent packs. This pack owns normalized payload contracts, identity mapping, ACL narrowing, route decisions, outbound draft approval state, preferences, and inbox UI contracts.

## Remote Input Authority

Remote input is evidence, not authority. It may create a normalized payload for review, but it cannot approve, execute, install packs, mutate settings, grant ACLs, issue approval tokens, issue security tokens, or trigger connector sends/fetches.

## Default Deny

Channel ACLs default to `deny`. Any request for work or outbound delivery must become a review or handoff packet unless a local reviewer and the correct owner pack complete their own approval flow.
