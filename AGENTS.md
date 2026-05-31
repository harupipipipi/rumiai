# Rumi AI Repository Guidance

These notes are for coding agents working in this repository.

## Orientation

- The canonical runtime implementation is `rumi_ai_1_10/`.
- The canonical defaultspack implementation is `rumi_ai_1_10/ecosystem/defaultspack/`.
- The canonical control-panel frontend is `rumi_ai_1_10/ecosystem/defaultspack/webapp/`.
- The desktop shell lives in `rumi_viewer/`; the mobile client lives in `rumi_mobile/`.

## Coding Workflow

- Use `rg` / `rg --files` first for source and file discovery.
- Keep changes tightly scoped to the requested runtime, pack, viewer, or mobile surface.
- Do not bypass approval, workspace jail, local guard, capability trust, or audit paths.
- Prefer adding small modules or helpers over growing central orchestration files.
- Preserve local-first behavior: defaultspack must start without cloud keys or network access.
- When provider/tool payloads change, keep schema normalization and provider quirks in `domain/tool/` or `domain/ai_client/provider_compiler/` rather than duplicating ad hoc fixes in call sites.

## Tests

- For defaultspack backend changes, run focused tests from `rumi_ai_1_10/`, for example:
  `python -m pytest tests/test_defaultspack_tool_protocol_v2.py -q`.
- For coding workspace or terminal changes, include:
  `python -m pytest tests/test_defaultspack_coding_hardening.py tests/test_defaultspack_terminal_policy.py -q`.
- For frontend changes, run from `rumi_ai_1_10/ecosystem/defaultspack/webapp/`:
  `npm test`, `npm run lint`, and `npm run build`.
- For Rust viewer changes, run the nearest `cargo test` in the changed crate.

## Security Expectations

- Client-supplied `approved` flags are not trusted for host, file, terminal, git, browser, or computer actions.
- Write-like tools, terminal execution, git commit/push, browser/computer control, and integration secrets must remain approval-aware.
- P2P or external input may request work, but local execution must still pass through the local policy and approval path.
