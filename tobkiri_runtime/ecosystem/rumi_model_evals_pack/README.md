# Rumi Model Evals Pack

Rumi Model Evals Pack is an optional, declarative, local-first pack for model evaluation and routing evidence. It defines provider smoke tests, layered contract/smoke/e2e eval suites, pass@k and pass^k metrics, flakiness tracking, model fit matrices, cost/latency evidence, and defaultspack promotion gates.

The pack reflects patterns from Cline-style layered evals and Hermes/OpenClaw-style provider catalogs and routing, while staying Rumi-native and non-executable.

## Provides

- Eval profiles for suite design, provider smoke checks, metric review, routing fit, and promotion gate review.
- Prompt contracts for interpreting eval evidence without overstating model quality.
- Presets for contract evals, provider smoke evals, coding-model routing, agent-service routing, and data-analysis model fit.
- Catalogs and specs for layered eval suites, metrics, provider overlays, fit matrices, and promotion gates.
- Examples for MiniMax/OpenCode Zen smoke checks, pass@k reporting, flakiness review, and defaultspack promotion evidence.

## Does Not Provide

- No executable eval runner, test harness, route, handler, notebook, or provider adapter.
- No provider keys, tokens, endpoints with credentials, or account-specific payloads.
- No network access by default.
- No mutation of defaultspack provider catalog entries. This pack supplies evidence overlays and advisory promotion gates.

## Documentation

Start with [docs/README.md](docs/README.md), then read [docs/architecture.md](docs/architecture.md), [docs/interfaces.md](docs/interfaces.md), and [docs/operations.md](docs/operations.md).
