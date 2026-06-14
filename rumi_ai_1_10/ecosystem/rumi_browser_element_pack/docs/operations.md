# Operations

## Setup

1. Install or select `rumi_default_tools_pack`.
2. Load `browser_extensions/rumi_browser_companion` in a Chromium browser.
3. Pair it through `browser_companion` with `action: bridge.pairing`.
4. Select this pack to enable browser element prompts and presets.

## Development Checks

- Validate JSON and YAML files.
- Run `python -m pytest tests/test_rumi_browser_element_pack_contract.py`.
- Run `python -m pytest tests/test_browser_companion.py` after changing extension semantics.

## Common Failures

- No connected client: pair the extension again.
- Missing content script: reload the target tab.
- Element not found: take a fresh snapshot and use `semantic_id`, `labels`, or a unique `selector_hint`.
- Unsafe form action: use a fresh snapshot entry and explicit approval evidence before submit-like clicks or Enter.
- Cross-origin frame: fall back to visible computer use or a CDP flow with frame access.
