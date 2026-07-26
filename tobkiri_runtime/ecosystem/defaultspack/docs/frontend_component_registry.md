# Frontend component registry contract

Declarative UI pieces resolve opaque component IDs through
`FrontendComponentRegistry`. A component ID is data, never a JavaScript expression,
module path, URL, or dynamic import target.

Every registration declares:

- `componentId` and `rumi.frontend.component.v1`
- supported shell/declarative slots
- JSON schemas for props, data, and action bindings
- allowed data-source and action IDs
- required permissions and a deterministic fallback component
- loader-owned source pack and trust metadata

The shipped generic components (`rumi.ui.text`, `rumi.ui.badge`, and
`rumi.ui.unsupported`) and approved pack-bundle components use the same registry and
resolution path. Pack code registration additionally requires an approved, verified
bundle, declared slots, and granted permissions. Template JSON cannot satisfy those
requirements by itself.

Resolution validates API version, slot, props, data, actions, and source IDs before a
React component is created. Unknown or invalid requests render the visible
`rumi.ui.unsupported` fallback. A React error boundary prevents a registered component
failure from breaking its parent surface. Diagnostics carry component, pack,
template, slot, trust, version/validation reason, and a stable error code.

Disabling or uninstalling a pack calls `unregisterSourcePack(packId)`. Built-in
entries are never removed by this operation and stale pack component IDs immediately
resolve to the unsupported fallback.

Backend action handlers remain authoritative. Registry action bindings contain only
registered action IDs and validated payload data; templates do not receive arbitrary
endpoint callbacks, credentials, filesystem handles, or approval authority.
