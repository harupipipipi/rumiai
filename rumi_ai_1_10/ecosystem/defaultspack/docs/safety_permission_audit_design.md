# Safety Permission Audit Design

Safety primitives:

- permission catalog
- allow, ask, deny policy
- risk classification
- approval gates
- workspace root enforcement
- network deny by default
- secret redaction
- audit log

Audit records include timestamp, actor, capability, operation, risk level, decision, and redacted arguments. Secret values are never written to audit records.

## Implemented local guard

defaultspack now treats local coding routes as sensitive HTTP operations. The
guard is local-operation protection, not user authentication.

The HTTP transport checks loopback clients, local origins, CSRF metadata for
sensitive mutations that include an Origin header, and per-route sensitivity.
The coding blocks then verify a signed approval token before performing writes,
destructive file operations, terminal medium/high-risk execution, git commit, or
git push.

Approval tokens are HMAC signed with a local runtime secret. Each token is bound
to:

- the operation name;
- a stable hash of the approved arguments;
- the approval request id;
- an expiry timestamp.

Tokens are one-time use. If the UI or caller changes the path, command, git
target, file content, or any other protected argument after approval, execution
is rejected and the failure is recorded.

## Audit storage

The local audit store is JSONL. By default it is written under
`ecosystem/defaultspack/user_data/audit/local_actions.jsonl`; tests or embedded
runtimes may override the path with `RUMI_DEFAULTSPACK_AUDIT_PATH`.

The audit layer records:

- attempts;
- approval creation and decisions;
- execution;
- denials;
- failures.

Arguments are redacted before persistence. Keys containing `api_key`,
`authorization`, `token`, `secret`, `password`, or `cookie` are replaced with a
redaction marker, including nested dictionaries and lists.
