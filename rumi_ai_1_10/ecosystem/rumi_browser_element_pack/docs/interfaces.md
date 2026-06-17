# Interfaces

## Required Tools

- `rumi_default_tools_pack:browser_companion`

## Expected Snapshot Fields

- `schema_version: semantic_dom_v2`
- `nodes[].element_id`
- `nodes[].semantic_id`
- `nodes[].accessible_name`
- `nodes[].labels`
- `nodes[].nearby_text`
- `nodes[].rect`
- `nodes[].is_in_viewport`
- `nodes[].flags`
- `nodes[].action_hints`
- `nodes[].selector_hint`
- `nodes[].xpath_hint`

## Grants

This pack itself requests no grants. The underlying browser companion remains high risk and requires the grants defined by `rumi_default_tools_pack`.

## Network

No direct network access. The extension talks only to the local bridge configured by the user.

## Overlap Rules

- Generic `browser_use` requests should prefer `browser_companion` when a paired extension is available.
- CDP/headless browser packs remain preferred for isolated testing.
- Visible computer-use drivers remain preferred when the page blocks extension scripts or cross-origin frames hide the target.
