# Architecture

`rumi_omnichannel_agent_inbox_pack` is a declarative setup pack. Its architecture has four layers:

1. Schema-bound input and output records.
2. Workflow catalogs that describe draft and handoff transitions.
3. Quality gates that block unsafe, uncited, or unapproved output.
4. Setup metadata that keeps defaultspack promotion false until real integration evidence exists.

The pack does not register functions, run servers, call tools, open browsers, mutate files, or contact external services.

Remote channel payloads are normalized before they reach this pack. The pack stores only redacted metadata contracts, route decisions, draft approval receipts, and handoff records. It has no provider client, no secret material, and no pre-auth HTTP surface.
