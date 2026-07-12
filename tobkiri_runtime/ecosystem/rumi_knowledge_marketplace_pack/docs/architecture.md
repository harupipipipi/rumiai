# Architecture

`rumi_knowledge_marketplace_pack` separates intent, evidence, policy, matching, and handoff.

1. Marketplace card schemas define what a skill, tool, MCP surface, template, playbook, extension, connector card, or pack bundle must disclose before it is install-ready.
2. Cards publish free-form discovery and compatibility tags. Stable card IDs remain provenance keys and are never used as opaque dependency selectors.
3. Requirement entries combine with AND; each entry uses `any` or `all` tag matching. Requirement kinds are open so future extension surfaces do not require a central enum migration.
4. Pack-first resolution checks approved installed packs before loose skills, tools, MCP descriptors, or extensions. Missing requirements produce a search or install-review handoff, never automatic installation.
5. Provider-independent model tiers describe how casually or carefully a model may be used. Concrete routing remains a defaultspack decision based on capability, quality, speed, and cost metadata.
6. Trust rubrics classify candidates as unreviewed, repository-reviewed, trusted, or blocked using provenance, permissions, publisher, and maintenance evidence.
7. Install-review workflows keep discovery, tag matching, permission review, provenance review, and install decisions separate.
8. Provenance ledgers record source refs, content digests, reviewers, review times, trust status, permission summaries, requirement evidence, install decisions, and blacklist status.
9. Promotion and blacklist policy prevents unreviewed or excessive-permission content from being treated as default behavior.
10. Setup metadata exposes dependencies, overlaps, marketplace status, signing status, and defaultspack promotion blockers.

The architecture keeps Rumi modular: each pack owns one domain and routes overlapping work to the pack that owns that surface.

`rumi_knowledge_marketplace_pack` does not install content, grant connector access, connect MCP servers, fetch remote repositories, or override `defaultspack`. It describes local review and matching contracts and routes execution to `rumi_connector_gateway_pack`, MCP review to `rumi_mcp_gateway_pack`, security review to `rumi_security_review_pack`, learned-skill persistence to `rumi_memory_knowledge_pack`, bundle composition to `rumi_pack_suite_pack`, and model routing to `defaultspack`.

The Tools workspace includes a non-executing Marketplace preview. `Coming soon` and a disabled `探す` action reserve the discovery route without implying that remote search or installation is available.
