# Architecture

## Responsibility

`rumi_research_pack` defines research and evidence contracts for Rumi-native agents. It is intentionally declarative: the pack names research capabilities, evidence records, source quality dimensions, citation expectations, prompts, profiles, presets, and examples. Concrete collection, browsing, file IO, connector access, and report rendering remain owned by runtime or tool packs.

The pack covers:

- Research planning and scope control.
- Evidence cards with claim, source, quote, confidence, and retrieval metadata.
- Source quality scoring and contradiction handling.
- Citation style preferences and traceable synthesis.
- Local-first research reports and decision briefs.

The pack does not own:

- Browser automation, scraping, remote search, connector sync, or external APIs.
- Long-running job execution.
- Workspace export/rendering implementation.
- Default runtime boot behavior.

## Main Directories

- `catalog/`: JSON/YAML declarations for research capabilities, evidence schemas, source quality, workflows, and citations.
- `profiles/`: runtime profile declarations for research and evidence review modes.
- `presets/`: higher-level research modes combining profiles, panels, and behavior hints.
- `prompts/`: system prompt fragments for research planning, evidence capture, citation discipline, and synthesis.
- `examples/`: task examples that show expected payload shape and deliverables.
- `docs/`: pack-specific docs required by the pack documentation contract.

## Execution Path

1. The setup selector discovers `ecosystem/setup_pack/rumi_research_pack/pack.json`.
2. Rumi loads `ecosystem/rumi_research_pack/ecosystem.json`.
3. Runtime or UI surfaces may read catalogs, profiles, presets, prompts, and examples as data.
4. Concrete tool packs decide whether they can satisfy capability names such as `research.plan.create`, `research.evidence.extract`, or `research.synthesis.write`.
5. Outputs remain local-first unless an implementation explicitly requests network or connector grants outside this pack.

## Runtime Touch Points

- `defaultspack`: supplies core runtime/profile conventions. This pack depends on it and does not replace it.
- `rumi_workspace_pack`: may consume research outputs as sources for documents, slides, sheets, PDFs, charts, or exports. This pack does not own workspace artifact rendering.
- `rumi_agent_services_pack`: may orchestrate long-running research jobs. This pack only declares research recipes and does not enqueue or execute services.
