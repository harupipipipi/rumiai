# API Key Node

The API Key Node manages multiple named keys per provider and lets agent/profile/model policy choose a key without exposing the secret.

## Storage

Metadata is stored in:

```text
user_data/shared/api_keys/keys.json
```

Secret values are stored through the secret store using each key's `secret_name`. API responses, logs, tool results, and usage reports return only `secret_preview` and redacted metadata.

## Schema

```yaml
key_id: openrouter_cheap_main
display_name: OpenRouter Cheap Main
provider_id: openrouter
enabled: true
secret_name: DEFAULTSPACK_API_KEY_OPENROUTER_CHEAP_MAIN
secret_preview: sk-or-...abcd
allowed_profiles: []
allowed_agents: []
allowed_models: []
limits:
  daily_usd: 1.0
  monthly_usd: 10.0
  daily_tokens: 2000000
  max_requests_per_minute: 20
  max_parallel_requests: 2
conditions:
  active: true
  active_hours: 00:00-23:59
  timezone: Asia/Tokyo
  fallback_key_ids: []
```

## Resolver Order

`KeyResolver` evaluates request context in this order:

1. explicit `preferred_key_id`
2. agent default key
3. profile default key
4. provider default key
5. legacy env/static key
6. fallback key

Disabled keys, model/profile/agent mismatches, exhausted budgets, and rate limits are skipped. If every candidate fails, the resolver returns a blocked result instead of a secret.

## Routes

| method | path |
|---|---|
| `GET/POST` | `/api/ai/keys` |
| `GET/PUT/DELETE` | `/api/ai/keys/{key_id}` |
| `POST` | `/api/ai/keys/{key_id}/test` |
| `GET` | `/api/ai/keys/{key_id}/usage` |

The AI client accepts `api_key_id`, `profile_id`, and `agent_id` in call context so Operations Company and local agents can share named keys safely.
