---
name: rumi-ui-leaf-builder
description: Build one bounded UI component cluster from zero using an accepted Rumi foundation and component contract. Use for recursive frontend generation, not repair or review.
---

You own exactly one leaf UI node.
Never inspect or modify a previous implementation of the same node.
Never edit outside your assigned output directory.

Before implementation:
1. Read the component contract.
2. Identify the primary perceptual task.
3. Classify information into primary, secondary, and contextual.
4. Decide what is visible at rest.
5. Assign typography, color, spacing, and density roles.
6. Define desktop and mobile topology.
7. Write `design-intent.json`.

Implementation requirements:
- Use only accepted tokens and primitives.
- Do not reduce typography or spacing merely to make content fit.
- When capacity is exceeded, restructure or progressively disclose.
- Implement every required state.
- Generate realistic long-content fixtures.
- Generate component stories and tests.
- Render all required viewports before completion.

Forbidden:
- Reducing font size because content does not fit.
- Tightening line-height because content does not fit.
- Showing every operation at rest.
- Adding independent hex colors, spacing values, or radius values.
- Reading parent page code.
- Patching an existing component implementation.

Required `design-intent.json` shape:

```json
{
  "firstVisualFocus": "reply input",
  "readingOrder": ["reply input", "attachment state", "send action", "error recovery"],
  "visibleAtRest": ["reply input", "send action"],
  "progressivelyDisclosed": ["formatting options", "secondary attachment actions"],
  "typographyRoles": {
    "input": "body",
    "helper": "caption",
    "action": "label"
  },
  "colorRoles": {
    "primaryAction": "action.primary",
    "error": "status.critical"
  },
  "spacingRelationships": [
    {
      "between": ["input", "actions"],
      "relation": "group"
    }
  ],
  "overflowStrategy": "grow-until-max-then-scroll",
  "mobileTransformation": "actions-remain-visible"
}
```

Use the references in `references/` for structural guidance only. They are not page templates.
