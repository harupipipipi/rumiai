# Tobkiri Subagent Placement Pack

Compiles Pack-declared Subagent Definitions and Placements into immutable,
revision-pinned Effective Subagent Plans.

The compiler reuses the selected Global Contract Registry and an existing
CapabilityPlan. Authority is the intersection of every non-empty allow layer,
denials are cumulative, budgets use the smallest limit, approval uses the
strictest level, and compiler stages cannot widen authority.

The product vocabulary remains Main Agent, subagent, Placement, and Team.
Pack-defined protocols and Placement features stay outside Core enums.
