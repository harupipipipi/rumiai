# Architecture

The pack has one responsibility: make DOM-grounded browser automation predictable.

## Directories

- `catalog/`: element schema and ranking guidance.
- `profiles/`: browser element agent profile.
- `prompts/`: system prompt for page inspection and action.
- `presets/`: selectable operating styles.
- `examples/`: concrete task recipes.

## Runtime Boundary

The pack depends on `rumi_default_tools_pack` for actual browser operations. It expects `browser_companion` to expose:

- `page.snapshot` with `semantic_dom_v2`
- `page.highlight`
- `page.clear_highlight`
- `page.click`, `page.type`, `page.press`, `page.scroll`, and `page.extract`

The pack should not duplicate browser control code. If another pack provides browser control, explicit pack namespaces win over generic aliases.
