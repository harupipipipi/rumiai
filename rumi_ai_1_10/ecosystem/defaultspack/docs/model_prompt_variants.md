# Model-declared prompt variants

Defaultspack can select a small prompt adapter after model routing by matching
model-declared prompt preferences with prompt-declared traits. This keeps base,
task, safety, memory, tool, and policy inputs unchanged while allowing models
with different instruction-following characteristics to receive different
wording.

The feature is opt-in. A profile without `metadata.prompt_selection` behaves as
it did before.

## Why slots and traits

A direct table such as `Claude -> claude.md` and `DeepSeek -> deepseek.md`
works initially, but it couples every prompt to model names and aliases. Prompt
traits describe the reason for the variant instead:

- `instruction.explicit`
- `instruction.concise`
- `format.strict`
- `format.light`
- `tool_guidance.explicit`
- `autonomy.high`
- `autonomy.low`

A semantic slot prevents contradictory variants from being attached together.
For example, only one prompt should normally win the
`model_instruction_adapter` slot.

## Runtime order

Model prompt selection happens in this order:

1. Build the normal profile AI input.
2. Route the request and determine the model that will receive it.
3. Read that model's prompt preferences.
4. Resolve trusted prompt candidates through the existing effective-prompt
   resolver.
5. Select one winner per `best_match` slot.
6. Append selected adapter text to the system input.
7. Run normal provider planning and degradation.

Because selection occurs after model routing, an automatically routed model is
matched against its own declaration rather than the conversation's stale
preferred model.

## Model declaration

A model catalog entry may declare preferences in `metadata`:

```json
{
  "id": "deepseek/deepseek-chat",
  "provider_id": "deepseek",
  "model_id": "deepseek-chat",
  "metadata": {
    "prompt_preferences": {
      "prefer": {
        "instruction.explicit": 100,
        "format.strict": 80,
        "tool_guidance.explicit": 70
      },
      "avoid": {
        "instruction.implicit": 100,
        "format.freeform": 40
      }
    }
  }
}
```

Simple arrays are also accepted and receive the default weight of `100`:

```json
{
  "metadata": {
    "prompt_preferences": {
      "prefer": ["instruction.concise", "autonomy.high"],
      "avoid": ["instruction.repetitive"]
    }
  }
}
```

Provider defaults may use the same declaration under the provider manifest
configuration:

```json
{
  "config": {
    "prompt_preferences": {
      "prefer": {
        "instruction.concise": 30
      }
    }
  }
}
```

Exact-model weights override provider weights for the same tag. Provider-only
tags remain in the merged declaration.

Weights must be positive integers. Invalid tags, zero or negative weights, and
values beyond the runtime limits are ignored or bounded during normalization.

## Prompt declaration

A trusted prompt component or pack prompt may declare its slot and traits in
manifest metadata:

```json
{
  "id": "model_adapter_explicit",
  "prompt_id": "model_adapter_explicit",
  "entrypoints": {
    "prompt": "prompt.md"
  },
  "metadata": {
    "prompt_selection": {
      "slot": "model_instruction_adapter",
      "tags": [
        "instruction.explicit",
        "format.strict",
        "tool_guidance.explicit"
      ],
      "priority": 20
    }
  }
}
```

Namespaced top-level fields are also accepted:

```json
{
  "metadata": {
    "prompt_slot": "model_instruction_adapter",
    "prompt_tags": ["instruction.concise", "autonomy.high"],
    "prompt_priority": 10,
    "prompt_fallback": false,
    "prompt_selection_mode": "best_match",
    "prompt_slot_priority": 100
  }
}
```

Generic fields such as top-level `tags` or `priority` do not opt a prompt into
selection. Generic aliases are accepted only inside `prompt_selection`, which
prevents unrelated component metadata from changing model input accidentally.

## Profile declaration

The startup profile defines the candidate pool:

```yaml
metadata:
  prompt_selection:
    slots:
      model_instruction_adapter:
        selection_mode: best_match
        slot_priority: 100
        fallback_prompt_id: model_adapter_default
        candidates:
          - model_adapter_explicit
          - model_adapter_autonomous
```

Prompt metadata can instead be supplied or overridden by the profile:

```yaml
metadata:
  prompt_selection:
    slots:
      model_instruction_adapter:
        candidates:
          - strict_local
          - autonomous_local
        fallback_prompt_id: default_local

    prompts:
      strict_local:
        tags:
          - instruction.explicit
          - format.strict
        priority: 20

      autonomous_local:
        tags:
          - instruction.concise
          - autonomy.high
        priority: 10

      default_local:
        fallback: true
        priority: -10
```

A candidate may select a prompt from another trusted pack explicitly:

```yaml
candidates:
  - prompt_id: company_strict_adapter
    source_pack_id: rumi_operations_company_pack
    tags:
      - instruction.explicit
    slot: model_instruction_adapter
```

Prompt content is still resolved through profile overrides, profile snapshots,
and trusted pack defaults in the normal order.

## Selection rules

For a `best_match` slot, the selector uses the following precedence:

1. An explicitly pinned candidate.
2. A candidate with a positive preferred-trait match.
3. A fallback candidate.
4. The highest deterministic score when no declaration matches.

The score is:

```text
sum(matched preferred weights)
- sum(matched avoided weights)
+ prompt priority
```

Ties are resolved by:

1. explicit selection;
2. total score;
3. preference-only score;
4. prompt priority;
5. number of preferred matches;
6. number of avoided matches;
7. stable prompt ID.

Catalog order and filesystem order therefore do not change the winner.

### Pinning a slot

A profile can pin one candidate:

```yaml
metadata:
  prompt_selection:
    slots:
      model_instruction_adapter:
        selected_prompt_id: model_adapter_explicit
        candidates:
          - model_adapter_explicit
          - model_adapter_autonomous
```

`pinned_prompt_id` is accepted as an alias. A pinned candidate wins that slot
even when another candidate has a higher trait score.

A prompt that is already active in the normal AI input and declares the same
slot is treated as an explicit selection. It is not duplicated in the provider
request. This preserves existing profile and safety behavior.

### Fallback

`fallback_prompt_id` is selected only when the slot has no explicit candidate
and no positive preferred-trait match. A high-priority unmatched prompt cannot
silently displace the declared fallback.

### Additive slots

Set every candidate in a slot to `selection_mode: all` or `additive` when the
slot is intentionally cumulative:

```yaml
metadata:
  prompt_selection:
    slots:
      provider_quirks:
        selection_mode: all
        candidates:
          - json_schema_hint
          - tool_calling_hint
```

Mixed `all` and `best_match` modes fail safe to `best_match` and emit a
selection diagnostic.

## DeepSeek and Claude example

A DeepSeek declaration may prefer explicit constraints:

```json
{
  "prompt_preferences": {
    "prefer": {
      "instruction.explicit": 100,
      "format.strict": 80
    }
  }
}
```

A Claude declaration may prefer concise, higher-autonomy framing:

```json
{
  "prompt_preferences": {
    "prefer": {
      "instruction.concise": 80,
      "autonomy.high": 70,
      "format.light": 50
    },
    "avoid": {
      "instruction.repetitive": 80
    }
  }
}
```

Both models keep the same base and task prompts. Only the adapter occupying
`model_instruction_adapter` changes.

## Observability

The request context receives a redacted `model_prompt_selection` record with:

- final and original model IDs;
- provider ID;
- normalized preference weights and declaration sources;
- selected and rejected prompt IDs;
- slot, tags, score components, and reason;
- diagnostics.

Prompt text, raw source paths, and private resolver metadata are excluded from
that compact record.

The existing AI input trace receives runtime prompt segments for selected and
rejected candidates. Rejected and already-counted candidates contribute zero
tokens to the effective token total, while their candidate token estimate is
kept in segment metadata for inspection.

## Trust and policy boundaries

Model prompt variants are text-only adapters.

They cannot:

- select or enable tools;
- grant permissions or approvals;
- choose a provider or model;
- change profile policy;
- bypass a disabled prompt edge;
- load content from an untrusted pack.

Candidate bodies use the existing effective-prompt resolver and pack trust
checks. Malformed metadata or resolution failures are fail-soft: normal model
input continues without the optional adapter, and diagnostics contain only an
error type rather than raw exception text.

## Non-goals

This feature does not add executable `if` or `else` syntax to Markdown. Prompt
files remain text. Conditions and composition remain profile/runtime concerns,
which keeps prompt content portable and auditable.
