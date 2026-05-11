# Response Adapters

Response adapters convert Rumi output into provider-specific replies. They are
the outbound half of the external input framework.

```text
runtime result
  -> ResponsePromptPolicy
  -> ResponsePlanner
  -> ResponsePlan
  -> ResponseAdapter
  -> provider API or HTTP response
```

The runtime should not know how to post to Slack, use a LINE reply token, or
format a Discord interaction response. It should return a provider-neutral
result that a planner can adapt.

## ResponsePlanner

`ResponsePlanner` decides what should happen with a runtime result:

- `reply_text`: send assistant text back to the source;
- `store_only`: keep the chat result without an external reply;
- `summarize_then_reply`: send a short bounded summary;
- `run_browser_use`, `run_computer_use`, `run_python`, `run_tool`: create a
  follow-up action plan, not a direct execution;
- `send_file_if_allowed`: allow normal file planning after capability checks;
- `ask_for_approval`: stop at an approval-required plan.

The planner reads the prompt decision, provider limits, event audience, and
runtime output metadata. Provider length limits, file limits, and sensitivity
checks still happen after the prompt decision.

Output profiles are the outbound counterpart to input profiles. Built-in
profiles cover LINE reply/push, Discord bot channel messages, Discord webhook
URLs, Slack channel/thread messages, generic webhook callbacks, and local web
output. Custom profiles can be placed in `user_data/shared/output_profiles`.
For built-in LINE/Discord/Slack outputs, setup is intentionally copy-paste plus
selection: choose an output template/profile, paste non-secret target ids into
the UI, and store bot tokens or webhook URLs as masked external tokens. Arbitrary
senders and free-form prompt instructions live under Custom.

## Response Prompt Policy

`response_prompt` is a prompt-routed planning policy. It may inspect the event,
input text, and runtime result, then return a `plan_only` decision for
`ResponsePlanner`, but it must not execute tools or call provider APIs directly.
The executable steps are created later through the existing tool policy,
approval, turn-runner, and response adapter paths.

Policy fields are defined in `schemas/response_prompt_policy.schema.yaml`:

- `allowed_actions`: the only `ResponsePlan.action` values the prompt may
  return;
- `tools`: tool visibility and approval requirements for planning context;
- `output_schema`: the expected structured shape of the prompt decision;
- `allowed_outputs`: optional output profile ids or providers the prompt may
  target;
- `fallback`: the safe action to use when the prompt output is invalid or
  denied;
- `sensitivity`: visibility defaults and external delivery constraints.

Any decision whose action is not listed in `allowed_actions` must be rejected
and handled through `fallback`.

Example:

```yaml
response_prompt:
  enabled: true
  model: inherit
  mode: plan_only
  allowed_actions:
    - reply_text
    - store_only
    - run_browser_use
    - run_python
  tools:
    browser_use:
      enabled: true
      requires_approval: false
    python:
      enabled: true
      requires_approval: false
      sandbox: true
    external_send:
      enabled: true
      requires_approval: true
  system_prompt: |
    Decide how Rumi should respond. Use browser_use only when current
    external information is needed. Return strict JSON.
  user_prompt: |
    Provider: ${event.provider}
    Scope: ${event.scope.type}:${event.scope.id}
    Actor: ${event.actor.id}
    User input: ${input.text}
    Assistant result: ${response.text}
```

For cross-provider actions, the prompt should return a plan such as
`run_tool` with `tool: external_send`. That tool is approval-gated and uses the
same LINE, Discord, Slack, and generic webhook adapters as normal response
delivery. The prompt never receives raw bot tokens or webhook secrets.

## ResponsePlan

Example plan:

```json
{
  "provider": "discord",
  "messages": [
    {
      "type": "text",
      "text": "Here is the summary..."
    }
  ],
  "metadata": {
    "response_prompt_decision": {
      "action": "reply_text",
      "sensitivity": "public"
    },
    "response_action_plan": {
      "type": "reply",
      "external_reply": true
    }
  }
}
```

Targets may contain provider identifiers, but not raw authorization values. Any
short-lived reply handle should be passed as an internal reference and resolved
inside the adapter.

## Adapter Responsibilities

A `ResponseAdapter` is responsible for:

- rendering provider-specific message shape;
- enforcing provider length limits;
- avoiding mass mentions unless policy allows them;
- rejecting actions outside the active response prompt policy;
- rechecking sensitivity and capabilities before external replies;
- resolving secret references from the secret store;
- calling provider APIs;
- returning redacted delivery status;
- mapping provider errors to stable framework errors.

Adapters may be sync or async. If the provider requires a fast HTTP response,
the webhook handler can return an ack while the adapter sends later.

## Built-In Adapter Targets

| Adapter | Delivery target |
|---|---|
| `slack-thread` | Slack `chat.postMessage` with optional `thread_ts` |
| `line-reply` | LINE reply API using a short-lived reply token reference |
| `discord-interaction` | Discord interaction response body |
| `discord-channel` | Discord channel message API |
| `discord-webhook` | Discord webhook URL |
| `webhook-json` | Generic JSON response or callback URL |
| `external_send` | Tool-backed LINE/Discord/Slack/generic send after approval |

The adapter id is selected by `InputProfile`, not by the chat handler.

## Error Behavior

Public channels should receive safe, short errors only when the profile allows
that behavior. Detailed provider errors belong in redacted logs or delivery
status, not in a channel reply.

Examples:

| Condition | Recommended action |
|---|---|
| Missing outbound token | redacted delivery error without raw secret |
| Provider rate limit | `store_only` or provider-specific deferred handling |
| Message too long | normal planner chunking |
| Policy denied after planning | `store_only` |

## Safety Rules

Response prompt policies are deny-by-default at the action boundary:

- `computer_use` requires explicit approval by default, even if it is visible in
  the planning context.
- Plans outside `allowed_actions` are refused before adapter delivery.
- `browser_use` must respect the active network policy.
- `python` follow-up plans must declare sandbox/local-only expectations.
- Before any external reply, the adapter path rechecks `sensitivity` and current
  capabilities so stale prompt output cannot leak local-only or secret content.
