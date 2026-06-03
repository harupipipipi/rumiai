# Architecture

The connector gateway has four layers.

1. Connector inventory records available surfaces, owner plugin, scopes, and data class.
2. Inbound classification separates user instructions, untrusted channel content, attachments, and connector metadata.
3. Handoff envelopes normalize work requests before agent services, workspace, scheduler, or security packs consume them.
4. Scope review cards make sensitive permissions explicit before grants or recurring workflows are used.

Transport code remains outside the pack. This prevents a policy pack from becoming a hidden credential or network owner.
