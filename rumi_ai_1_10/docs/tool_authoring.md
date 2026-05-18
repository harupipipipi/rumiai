# Tool Authoring

A tool needs a manifest, callable function or tool entrypoint, risk level, permission requirements, UI metadata, and model compatibility notes.

Function blocks are internal callable units. Tools expose user-visible capabilities and may be invoked by tool-calling models. High-risk tools include file writes, deletion, terminal execution, network mutation, browser/computer control, and credential changes.

Tool manifests should state required permissions, approval needs, input/output schemas, and UI labels. Tool-calling compatibility must be checked against selected model capabilities before the AI request is built.
