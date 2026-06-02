set positional-arguments

# Display available commands.
help:
    just -l

# Run the package health check.
health:
    python -m rumi_ai --health

# Run root-level contract tests.
root-test *args:
    pytest tests/ "$@"

# Run rumi_ai_1_10 tests. Pass pytest selectors after the recipe name.
test *args:
    cd rumi_ai_1_10 && python -m pytest "$@"

# Run the focused defaultspack coding/tooling regression cluster.
tooling-test:
    cd rumi_ai_1_10 && python -m pytest \
        tests/test_defaultspack_provider_tool_schema.py \
        tests/test_defaultspack_tool_protocol_v2.py \
        tests/test_defaultspack_terminal_policy.py \
        tests/test_defaultspack_coding_hardening.py -q

# Run Python static checks over the backend surfaces guarded in CI.
lint:
    cd rumi_ai_1_10 && python -m ruff check core_runtime backend_core ecosystem/defaultspack/domain/coding ecosystem/defaultspack/domain/tool ecosystem/defaultspack/blocks/coding app.py
    cd rumi_ai_1_10 && python -m mypy --check-untyped-defs core_runtime backend_core ecosystem/defaultspack/domain/coding ecosystem/defaultspack/domain/tool ecosystem/defaultspack/blocks/coding app.py

# Run defaultspack frontend checks.
frontend-check:
    cd rumi_ai_1_10/ecosystem/defaultspack/webapp && npm test
    cd rumi_ai_1_10/ecosystem/defaultspack/webapp && npm run lint
    cd rumi_ai_1_10/ecosystem/defaultspack/webapp && npm run build

# Run the defaultspack integrity scan used by CI.
integrity:
    cd rumi_ai_1_10 && python scripts/quality/scan_defaultspack_integrity.py
