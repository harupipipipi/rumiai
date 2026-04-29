# Artifact Generation Design

Artifacts are local deliverables with metadata:

- markdown, text, code
- json, yaml, html, csv
- report, changelog, implementation plan

Each artifact has `artifact_id`, `type`, `title`, `path`, `content_ref`, `created_by`, `source_task`, and `version`. Artifact save uses the local file capability and can be exported later by optional adapters.
