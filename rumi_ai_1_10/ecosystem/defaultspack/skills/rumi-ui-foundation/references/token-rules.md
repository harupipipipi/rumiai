# Foundation Token Rules

## Allowed Token Families

- Color: semantic surfaces, text, borders, focus, status, and accent roles.
- Typography: font families only when local or system-safe, size steps, line heights, weights.
- Spacing: layout gaps, control gaps, section padding, dense/comfortable aliases.
- Shape: radii, border widths, focus rings.
- Elevation: shadows or outlines by purpose.
- Motion: durations and easing only, with reduced-motion fallback.
- Breakpoints and layout constants: named viewport thresholds and max widths.
- Z-index: named layers for shell, popover, modal, toast, and drag surfaces.

## Token-Only Acceptance Rules

An accepted foundation must contain only tokens and token delivery plumbing. It must not contain:

- Components, JSX, HTML templates, render functions, or page sections.
- Leaf internals, slot implementations, routing, data fetching, or state machines.
- User-facing copy beyond token labels or comments.
- Fixture data, API mocks, screenshots, generated images, or brand assets.
- Hard-coded component decisions such as "this toolbar has three buttons".

## Rejection Rules

Reject the foundation when:

- A token is named by raw value instead of role, such as `blue500ForSubmitOnly`.
- A token creates a one-off escape hatch for one candidate instead of a reusable semantic role.
- Values require unavailable remote resources.
- Tokens cannot support default, long, empty, loading, error, required viewport, and required text-scale scenarios.
- Leaves or pages are expected to invent missing values locally.
