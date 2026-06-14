# Rumi Browser Automation Pack

Rumi Browser Automation Pack adds declarative browser task playbooks for pages that need real interaction: form completion, authenticated UI checks, visual regression, data collection, and recovery after page state changes.

The pack is intentionally not a browser driver. `rumi_default_tools_pack` continues to own the browser companion bridge, and `rumi_browser_element_pack` owns semantic DOM interpretation when it is installed. This pack owns the planning layer: what to inspect, what evidence to capture, when to stop, and how to avoid repeating unsafe browser actions.

## Required Secrets

None.

## Overlap Policy

- `defaultspack` owns grants, approvals, audit logs, and active pack selection.
- `rumi_default_tools_pack` owns browser companion execution.
- `rumi_browser_element_pack` owns semantic DOM v2 element understanding.
- `rumi_agent_services_pack` may call these playbooks, but this pack remains the source of browser automation policy.
