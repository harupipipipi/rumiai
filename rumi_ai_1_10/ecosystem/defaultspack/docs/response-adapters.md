# Response Adapters

Response adapters convert Rumi output into provider-specific replies. They are
the outbound half of the external input framework.

```text
runtime result
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

- `reply`: send text or blocks back to the source;
- `ack`: acknowledge without visible reply;
- `ignore`: do nothing;
- `defer`: answer later through an async adapter path;
- `split`: divide a long response into multiple provider messages;
- `truncate`: send a bounded response with a marker;
- `error`: send a safe failure message or suppress public output.

The planner reads `InputProfile.response`, provider limits, event audience, and
runtime output metadata.

## ResponsePlan

Example plan:

```json
{
  "action": "reply",
  "adapter_id": "slack-thread",
  "target": {
    "channel_id": "C123",
    "thread_id": "1700000000.000100"
  },
  "messages": [
    {
      "type": "text",
      "text": "Here is the summary..."
    }
  ],
  "metadata": {
    "source_event_id": "evt_01"
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
| `webhook-json` | Generic JSON response or callback URL |

The adapter id is selected by `InputProfile`, not by the chat handler.

## Error Behavior

Public channels should receive safe, short errors only when the profile allows
that behavior. Detailed provider errors belong in redacted logs or delivery
status, not in a channel reply.

Examples:

| Condition | Recommended action |
|---|---|
| Missing outbound token | `ack` plus redacted delivery error |
| Provider rate limit | `defer` or `error` based on profile |
| Message too long | `split` or `truncate` |
| Policy denied after planning | `ignore` |

