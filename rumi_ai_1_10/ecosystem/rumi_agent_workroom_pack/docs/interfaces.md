# Interfaces

    ## Inputs

    - Local user-supplied artifacts or records emitted by adjacent owner packs.
    - Schema IDs listed in `ecosystem.json`.
    - Evidence IDs, review state, and handoff owner labels.

    ## Outputs

    - Draft packets.
    - Review checklist packets.
    - Handoff packets for owner packs.
    - UI contract templates for host surfaces to render.

    ## Optional Integrations

    - `rumi_default_tools_pack`: Owns concrete tool execution after the workroom emits approved handoff packets.
    - `rumi_agent_services_pack`: Owns adjacent agent-service choreography after the workroom emits approved handoff packets.
- `rumi_browser_automation_pack`: Owns browser operations and page interaction runtime.
- `rumi_computer_control_pack`: Owns desktop actions and computer seat runtime.
- `rumi_workflow_scheduler_pack`: Owns timers, reminders, and recurring run wakeups.
- `rumi_workspace_pack`: Persists files and exports run artifacts.
- `rumi_observability_pack`: Collects run metrics and traces.
- `rumi_subagent_pr_manager_pack`: Owns PR orchestration across subagents.
- `rumi_model_catalog_pack`: Owns model availability and model-routing policy.

    ## Required Secrets

    None.

    ## Does Not Provide

    - tool execution
- browser action
- desktop action
- schedule execution
- file persistence
- metrics collection
- subagent PR management
- model routing
