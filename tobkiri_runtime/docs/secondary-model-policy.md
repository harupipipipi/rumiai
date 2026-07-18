# Secondary runtime model policy

Tobkiri uses `tobkiri.secondary-model-policy.v1` for model calls that are not
the primary conversation turn, including utility subagents, delegated agents,
and review-chain members.

## Model policy

```json
{
  "model_policy": {
    "mode": "inherit_conversation",
    "profile_id": "",
    "fallback_profile_id": "",
    "snapshot_profile_id": "",
    "required_capabilities": ["model.tool_calling"],
    "on_unavailable": "error"
  }
}
```

- `inherit_conversation` resolves the current conversation profile for every
  invocation. A turn override wins when one is present.
- `fixed` requires `profile_id` and stays pinned. It fails closed when the
  profile is unknown, unavailable, missing its API key, or lacks a required
  capability. A fallback is used only when `fallback_profile_id` is explicitly
  declared with `on_unavailable: fallback` (the default when a fallback exists).
- `snapshot` captures the conversation profile when the workflow is created.
  Persist the returned `snapshot_profile_id` with the workflow and supply it on
  later invocations.
- `auto_route` delegates the concrete choice to the canonical model router.

Legacy raw `model` fields remain compatible, but new secondary runtimes should
send the structured policy so catalog, availability, and capability preflight
is enforced before provider invocation.

## Thinking policy

```json
{
  "thinking_policy": {
    "mode": "inherit_conversation",
    "level": ""
  }
}
```

- `inherit_conversation` follows the turn, conversation, then global level.
- `fixed` requires one of `none`, `low`, `medium`, `high`, or `xhigh`.
- `model_default` uses the selected profile's declared default.

Unsupported fixed levels fail before invocation. Provider-native translation
continues in the provider compiler and is recorded separately from the generic
requested/resolved level.

## Resolution and replay

The shared precedence is:

1. turn override, where the selected mode permits an override;
2. the requested fixed/snapshot/inherit policy;
3. conversation profile;
4. global preferred profile;
5. canonical auto-routing.

Each invocation returns a `model_policy_receipt` containing the normalized
requested policies, concrete profile, provider/model identifiers, capability
requirements, fallback reason, and thinking resolution. Delegated-agent output,
utility-subagent events, and Rumi review-process metadata retain this receipt.

For deterministic replay, pass the prior receipt with
`replay_mode: deterministic` (or `strict`). The recorded concrete profile wins
over a later conversation-model change.

## Verification checklist

- Exercise inherit, fixed, snapshot, fallback, unavailable-provider, missing-key,
  capability-mismatch, and unsupported-thinking paths.
- Confirm all secondary calls expose a receipt and no raw API key is included.
- Confirm the Settings model picker offers both the current-conversation policy
  and explicit canonical model profiles.
