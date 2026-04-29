# Safety Permission Audit Design

Safety uses permission catalogs, allow/deny/ask policies, risk labels, approval gates, audit logs, sandbox root enforcement, secret redaction, and environment masking.

Default risky actions are writes, deletes, terminal commands, network use, git push, memory deletion, and policy changes. The `safety` capability describes these operations for UI and tool policy.
