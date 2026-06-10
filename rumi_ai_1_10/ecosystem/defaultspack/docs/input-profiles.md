<!-- docs-i18n-links:start -->
[EN](./input-profiles.md) | [JP](./i18n/ja/input-profiles.md) | [KR](./i18n/ko/input-profiles.md) | [CN](./i18n/zh-cn/input-profiles.md)
<!-- docs-i18n-links:end -->

# Input Profiles

An `InputProfile` describes how an allowed `ExternalEvent` becomes runtime input.
It is the bridge between external audience context and Rumi behavior.

Profiles keep provider edge code small. Webhook handlers normalize events;
profiles choose what Rumi should do with those events.

## Responsibilities

An input profile selects:

- destination type: chat, agent, flow, or ignore;
- conversation key strategy;
- model and prompt defaults;
- memory and context policy;
- response adapter;
- allowed event kinds;
- text transforms and attachment handling;
- fallback behavior when the event cannot be answered.

Profiles do not store raw secret values. They may reference secret names or
credential ids.

## Example

```json
{
  "id": "slack-support-thread",
  "enabled": true,
  "provider": "slack",
  "match": {
    "team_id": "T123",
    "channel_id": "C_SUPPORT",
    "event_kinds": ["message", "app_mention"]
  },
  "audience_policy_id": "support-channel-policy",
  "destination": {
    "type": "chat",
    "conversation_kind": "external",
    "session_key": "slack:{team_id}:{channel_id}:{thread_id}"
  },
  "runtime": {
    "model": "stub/default",
    "system_prompt_id": "support_assistant"
  },
  "response": {
    "adapter_id": "slack-thread",
    "mode": "reply"
  }
}
```

## Audience Policy Link

`AudiencePolicy` answers "may this event enter Rumi?".
`InputProfile` answers "what should Rumi do with it?".

A profile should reference a policy rather than embedding broad allow rules.
This keeps moderation, rate limits, and audience gates reusable across multiple
profiles.

## Session Keys

Profiles should produce stable session keys so external conversations map back
to existing Rumi conversations:

| Provider | Example session key |
|---|---|
| Slack thread | `slack:{team_id}:{channel_id}:{thread_id}` |
| Slack DM | `slack:{team_id}:dm:{user_id}` |
| LINE source | `line:{source_type}:{source_id}` |
| Discord channel | `discord:{guild_id}:{channel_id}` |
| Generic webhook | `webhook:{profile_id}:{external_subject}` |

The session key is not a credential. It can be logged if it contains no secret
or sensitive message content.

## submit_input Payload

`submit_input` should receive the normalized event and selected profile:

```json
{
  "event": {
    "event_id": "evt_01",
    "provider": "slack",
    "text": "summarize the thread"
  },
  "profile": {
    "id": "slack-support-thread",
    "destination": {"type": "chat"}
  },
  "policy": {
    "decision": "allow"
  }
}
```

The function returns a provider-neutral runtime result. Provider delivery is
handled later by `ResponsePlanner` and `ResponseAdapter`.

## Profile Safety Defaults

- default to disabled until explicitly enabled;
- require verified events unless a local dev flag is active;
- ignore bot/self messages by default;
- use least-privilege model, tool, and agent settings;
- prefer no response over an unsafe public response;
- redact metadata before audit or UI display.
