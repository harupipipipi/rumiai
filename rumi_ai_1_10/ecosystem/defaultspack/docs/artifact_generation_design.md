# Artifact Generation Design

Artifacts are durable outputs generated from conversations or agent runs. Supported types are markdown, text, code, json, yaml, html, csv, report, changelog, and implementation_plan.

Each artifact has an id, type, title, path, content reference, source task, creator, and version. Saving to workspace goes through local file capability and approval policy.
