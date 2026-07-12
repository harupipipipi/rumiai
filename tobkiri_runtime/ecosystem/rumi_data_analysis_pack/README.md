# Rumi Data Analysis Pack

Rumi Data Analysis Pack is an optional, declarative, local-first pack for data analysis workflows. It covers CSV, spreadsheet exports, local SQL datasets, notebook-style analysis, chart specifications, data cleaning recipes, and audit trails.

The pack is influenced by ChatGPT data analysis, Gemini data workflows, Claude artifacts, and Manus/Genspark report flows, but it stays Rumi-native: profiles, prompts, presets, catalogs, examples, and reproducibility contracts instead of executable tools.

## Provides

- Data analysis profiles for intake, cleaning, SQL, notebook reasoning, charting, audit review, and report synthesis.
- Prompt contracts for inspecting datasets, declaring assumptions, cleaning data, checking joins, choosing charts, and reporting limits.
- Presets for CSV exploration, spreadsheet audit, SQL question answering, notebook narrative analysis, chart design, and executive data reports.
- Catalogs for supported local data shapes, analysis capabilities, and chart kinds.
- Declarative recipes and specs for repeatable transformations, chart handoffs, and audit trails.

## Does Not Provide

- No executable Python, SQL runner, notebook kernel, route, handler, store, or function.
- No network access by default.
- No secrets, credentials, OAuth clients, database passwords, or vendor-specific keys.
- No final office artifact ownership. `rumi_workspace_pack` owns final documents, slides, spreadsheets, and export packaging when installed.

## Documentation

Start with [docs/README.md](docs/README.md), then read [docs/architecture.md](docs/architecture.md), [docs/interfaces.md](docs/interfaces.md), and [docs/operations.md](docs/operations.md).
