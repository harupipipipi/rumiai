# Operations

    Operators should treat this pack as a review and planning layer. If an operation would browse, write files, render office artifacts, mutate code, schedule work, store memory, or call a connector, the pack must emit a handoff packet for the owner pack instead.

    ## Does Not Provide

    - CLI IDE command loops
- file editing and patch execution
- subagent assignment and PR execution
- release notes and deploy runbooks
- security findings
- model provider scoring
- runtime telemetry storage
