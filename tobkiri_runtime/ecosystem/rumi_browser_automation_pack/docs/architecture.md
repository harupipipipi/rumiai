# Architecture

The pack is split into four layers.

1. Intent routing maps a user request to a browser playbook.
2. Observation requests page snapshots, screenshots, visible text, and optional semantic DOM nodes.
3. Action planning selects bounded actions such as click, type, select, wait, scroll, highlight, or screenshot.
4. Evidence capture records before and after state so the agent can explain what happened.

The pack never bypasses approval or transport. Browser execution is delegated to default tools. If the browser element pack is present, semantic IDs are preferred over brittle selectors. If it is absent, the pack asks for visible labels and screenshots before operating.
