# Architecture

`rumi_knowledge_marketplace_pack` separates intent, evidence, policy, and handoff.

1. Marketplace card schemas define what a skill, template, playbook, connector card, or pack bundle must disclose before it is install-ready.
2. Trust rubrics classify candidates as unreviewed, repository-reviewed, trusted, or blocked using provenance, permissions, publisher, and maintenance evidence.
3. Install-review workflows keep discovery, permission review, provenance review, and install decisions separate.
4. Provenance ledgers record source refs, content digests, reviewers, review times, trust status, permission summaries, install decisions, and blacklist status.
5. Promotion and blacklist policy prevents unreviewed or excessive-permission content from being treated as default behavior.
6. Setup metadata exposes dependencies, overlaps, marketplace status, signing status, and defaultspack promotion blockers.

The architecture keeps Rumi modular: each pack owns one domain and routes overlapping work to the pack that owns that surface.

`rumi_knowledge_marketplace_pack` does not install content, does not grant connector access, does not fetch remote repositories, and does not override `defaultspack`. It describes local review contracts and routes execution to `rumi_connector_gateway_pack`, security review to `rumi_security_review_pack`, learned-skill persistence to `rumi_memory_knowledge_pack`, and bundle composition to `rumi_pack_suite_pack`.
