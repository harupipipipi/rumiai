# /goal slash command

`/goal <description>` runs a goal-pursuit loop in the defaultspack console without direct tool execution:

1. A **Worker** agent produces the next concrete contribution toward the goal.
2. After each Worker turn, an independent third-party **Evaluator** agent
   checks whether the goal has been achieved.
3. If the goal is not yet achieved, the Evaluator returns a fresh
   `next_instruction`, and the Worker is prompted again.
4. The bounded loop stops when the Evaluator marks the goal as achieved or when the
   `max_iterations` cap is hit (default `5`, hard cap `20`).

## Rich / unbounded mode

`/goal /rich <description>` switches the command to rich mode. Rich mode removes
the `max_iterations` hard cap and loops until the Evaluator marks the goal
achieved or a Worker/Evaluator model call fails.

Equivalent forms:

```text
/goal /rich Ship the approval window without deferring work
/goal Ship the approval window without deferring work max_iterations=rich
/goal Ship the approval window without deferring work rich=true
```

In rich mode the result envelope reports:

```json
{
  "mode": "rich",
  "rich": true,
  "max_iterations": null,
  "hard_cap": null,
  "stopped_reason": "achieved"
}
```

Rich mode intentionally has no built-in iteration ceiling. It should only be used
when the caller is prepared for the goal loop to continue until success or an
error. The block still does not execute tools directly; it only makes model calls.

## Arguments

| Name             | Type    | Required | Default | Description                                                                 |
|------------------|---------|----------|---------|-----------------------------------------------------------------------------|
| `goal`           | string  | yes      | —       | Free-form description of the goal the Worker should pursue.                 |
| `max_iterations` | string  | no       | `5`     | Maximum worker/evaluator round-trips. Clamped to 1–20 unless set to `rich`. |
| `model`          | string  | no       | active  | Optional model hint passed to both Worker and Evaluator turns.              |
| `rich`           | string  | no       | false   | Enables unbounded rich mode when truthy.                                    |
| `mode`           | string  | no       | bounded | Enables rich mode when set to `rich`.                                       |

The slash command is registered in
[`commands/manifests/goal.json`](../commands/manifests/goal.json) and the
behavior lives in [`blocks/goal/run.py`](../blocks/goal/run.py).

## Result envelope

On success the command returns:

```json
{
  "status": "ok",
  "data": {
    "command": { "...": "manifest fields" },
    "executed": true,
    "result": {
      "goal": "Write a haiku about programming",
      "achieved": true,
      "reason": "Three-line haiku produced as requested.",
      "iterations": [
        {
          "iteration": 1,
          "worker_output": "...",
          "verdict": { "achieved": true, "reason": "...", "next_instruction": "" }
        }
      ],
      "iteration_count": 1,
      "final_output": "...",
      "max_iterations": 5,
      "rich": false,
      "mode": "bounded",
      "hard_cap": 20,
      "stopped_reason": "achieved"
    }
  }
}
```

When the bounded loop hits `max_iterations` without achieving the goal,
`achieved` becomes `false` and `stopped_reason` is `"max_iterations_reached"`.
When the Worker or Evaluator model call fails the command returns
`status: "error"` with `code: "WORKER_FAILED"` or `code: "EVALUATOR_FAILED"`
and an `iterations` array recording any partial progress.

## Related: /rule

`/rule <text>` pins a persistent conversation rule in the defaultspack rule
store. The rule is stored outside chat messages, so message-range compaction does
not delete the stored rule record.

Examples:

```text
/rule この会話では次PRに回さず、1PRで完結させる。
/rule action=list
/rule action=disable rule_id=rule_...
```

## Extensibility note: `pack_block` execution type

After the `pack_block` hook is in place, `/goal` itself is implemented through file additions:

* `commands/manifests/goal.json` declares the slash command.
* `blocks/goal/run.py` implements the goal-pursuit loop.

The feature is wired up via the `pack_block` execution type in
`SlashCommandRegistry`, which lets a manifest dispatch to a Python block under
`blocks/<dotted.path>` exposing `run(input, context) -> dict`.

This block does not execute tools directly; it only makes model calls for the
Worker and Evaluator turns.
`pack_block` is allowed only for `default` and `pack` manifest origins (never
for user manifests under `user_data/shared/commands/`), so untrusted command
manifests cannot load arbitrary modules.

Future slash commands that need backend behavior can now be added by:

1. Dropping a manifest into `commands/manifests/<command>.json`.
2. Dropping a block at `blocks/<area>/<file>.py` exposing a `run` callable.

No existing files need to change for those additions.
