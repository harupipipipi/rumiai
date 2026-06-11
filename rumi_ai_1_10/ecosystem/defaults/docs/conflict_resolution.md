<!-- docs-i18n-links:start -->
[EN](./conflict_resolution.md) | [JP](./i18n/ja/conflict_resolution.md) | [KR](./i18n/ko/conflict_resolution.md) | [CN](./i18n/zh-cn/conflict_resolution.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS Defaults Conflict Resolution

As the Rumi AI OS ecosystem grows, multiple packs will inevitably offer similar functionality (e.g., `tool_search`, `file_editor`). This document details how the `defaults` pack handles naming collisions, user preferences, and secure feature imports to guarantee stability and prevent malicious hijacking.

## Naming Collisions

When two or more installed packs declare an entity (tool, flow, agent) with the same identifier, the system must resolve it reliably without crashing.

### 1. The Preference Hierarchy (Priority Rules)
The core engine resolves names based on the following strict priority:
1.  **User Overrides (`user_data/preferences.json`):** If a user explicitly maps an identifier to a specific pack (e.g., `"search_tool": "com.example.advanced_search"`), it wins absolutely.
2.  **Explicit Pack Prefixing:** Packs should prefix their identifiers internally, but components can be called by their short name. If conflicts exist, the caller must use the fully qualified name (e.g., `rumi.tools.search` vs `my_company.tools.search`).
3.  **Installed Pack Priorities:** The `defaults` pack provides a UI for managing installed packs. Users can set a global "Pack Priority Order". If Pack A has higher priority than Pack B, Pack A's tool wins.
4.  **The Built-in Default Fallback:** If a requested component is missing or fails, the core system falls back to the `defaults` pack implementation.

### 2. User Prompts for Ambiguity
If an Agent tries to call a tool named `calculator`, and both `pack_a` and `pack_b` provide it *without* a clear priority rule set, the following occurs:
*   The `defaults` pack pauses the execution flow.
*   A UI modal pops up, asking the user to choose the preferred implementation and save it as a rule.
    *   *Prompt:* "Both Pack A and Pack B provide 'calculator'. Which should be used for this request, or permanently?"

## Import Permissions

Rumi AI OS relies on Python libraries and other packs. To adhere to the "Assume Malice" principle, pack imports must be strictly controlled.

### 1. The Sandbox Restriction
Packs run in an isolated environment. They cannot simply `import os` or `require('fs')` loosely.

### 2. Capabilities as Import Grants
As outlined in the core OS documentation, importing a feature or accessing a system resource requires a Capability Grant. The `defaults` pack manages the UI for this request.
*   **Requesting Access:** When a pack is installed or executed for the first time, its `ecosystem.json` declares required capabilities (e.g., `rumi.fs.read`, `external.python.requests`).
*   **The Approval Flow:** The `defaults` pack handles the user approval dialog. The user is presented with exactly *what* the pack wants to do and *why*.
    *   If granted, the system provisions an egress proxy or a specialized socket, not direct code execution privileges.
    *   If denied, the pack must "fail-soft", meaning the overarching application (like the Chat flow) continues without crashing, perhaps with a warning message.

### 3. Pack-to-Pack Imports (Dependency Resolution)
If `pack_a` wants to use a function from `defaults` or `pack_b`, it follows the Dependency Resolution mechanics.
*   **Approval:** The user must approve that `pack_a` is allowed to invoke `pack_b`'s public interface, ensuring one pack cannot invisibly orchestrate another malicious action.
