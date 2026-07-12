# Architecture

## Responsibility

Rumi Data Analysis Pack describes how Rumi should plan, reason about, document, and hand off data analysis work. It owns analysis intent, cleaning recipes, audit trails, chart specifications, and reproducible data notes.

It does not own final office artifacts. When `rumi_workspace_pack` is installed, that pack owns final documents, decks, spreadsheets, exports, and workspace artifact lifecycle. This pack hands it structured findings, chart specs, table summaries, and audit notes.

## Directory Map

- `ecosystem.json`: declarative component inventory and load-order hints.
- `catalog/capabilities.yaml`: local-first analysis capability catalog.
- `catalog/chart_kinds.json`: chart kind selection metadata.
- `profiles/`: runtime profiles for data analysis roles.
- `prompts/`: system prompts that define role behavior.
- `presets/`: named analysis experiences inspired by modern data assistants.
- `recipes/`: repeatable transformation and analysis recipes.
- `specs/`: chart spec and audit trail schemas.
- `examples/`: sample task specs for CSV, Sheets, SQL, notebooks, charts, and reports.
- `docs/`: pack-specific documentation required by the pack documentation contract.

## Runtime Contact Points

This pack expects existing Rumi capabilities to provide execution when a runtime chooses to act:

- `defaultspack`: chat, planning, approval, memory, artifacts, and flow runtime basics.
- `rumi_default_tools_pack`: file reading, calculation, local search, terminal or notebook execution if enabled by policy.
- `rumi_local_agent_pack`: local agent profiles and prompt conventions.
- `rumi_workspace_pack`: optional recipient for final office artifacts.

The pack references capability names and schema files only. It does not import or implement runtime code.

## Workflow Model

The intended analysis loop is:

1. Intake: capture question, files, grain, data dictionary, privacy boundary, and expected output.
2. Profile: identify dataset shape, columns, keys, missingness, units, date ranges, and joins.
3. Clean: declare reversible cleaning steps and assumptions before applying them.
4. Analyze: compute or reason through aggregations, comparisons, distributions, trends, outliers, and uncertainty.
5. Visualize: produce chart specs with chart intent, encodings, filters, annotations, and accessibility notes.
6. Audit: record provenance, transformations, checks, limitations, and reproducibility status.
7. Deliver: return findings, recipes, chart specs, and optional workspace artifact handoff payloads.

## Local-First Boundary

Network is none by default. Data comes from local files, pasted tables, exported spreadsheets, local database descriptors, or user-provided snapshots. Any runtime that executes SQL, terminal commands, notebooks, or writes files must use approval and sandbox policy outside this pack.
