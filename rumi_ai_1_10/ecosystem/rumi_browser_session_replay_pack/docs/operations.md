# Operations

Operators should treat this pack as a review and planning layer. If an operation would browse, click, type, submit, call the browser companion, write files, render artifacts, mutate code, schedule work, store memory, or call a connector, the pack must emit a handoff packet for the owner pack instead.

This pack does not execute browser actions. It reviews trace contracts, validates redaction state, links DOM and screenshot evidence, and prepares replay manifests that runtime owners can decide whether to execute.

## Does Not Provide

- browser execution
- semantic DOM interpretation
- browser companion transport
- form submission
- defaultspack audit and grants
- observability metric storage
- connector retrieval

## Operational Gates

- Redaction receipt is required before sharing browser evidence outside the local review context.
- Inline binary screenshots are blocked; evidence must use artifact refs plus checksums.
- Selector drift reports require both DOM evidence refs and screenshot evidence refs.
- Replay manifests must name `rumi_browser_automation_pack` as execution owner and `rumi_default_tools_pack` as transport owner.
