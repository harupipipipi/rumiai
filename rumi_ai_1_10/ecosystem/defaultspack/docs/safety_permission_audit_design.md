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
