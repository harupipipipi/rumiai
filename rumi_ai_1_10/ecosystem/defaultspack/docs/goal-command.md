# /goal slash command

`/goal <description>` runs a goal-pursuit loop in the defaultspack console without direct tool execution:

1. A **Worker** agent produces the next concrete contribution toward the goal.
2. After each Worker turn, an independent third-party **Evaluator** agent
   checks whether the goal has been achieved.
3. If the goal is not yet achieved, the Evaluator returns a fresh
   `next_instruction`, and the Worker is prompted again.
4. The loop stops when the Evaluator marks the goal as achieved or when the
   `max_iterations` cap is hit (default `5`, hard cap `20`).

## Arguments

| Name             | Type    | Required | Default | Description                                                                 |
|------------------|---------|----------|---------|-----------------------------------------------------------------------------|
| `goal`           | string  | yes      | —       | Free-form description of the goal the Worker should pursue.                 |
| `max_iterations` | string  | no       | `5`     | Maximum worker/evaluator round-trips. Clamped to 1–20.                      |
| `model`          | string  | no       | active  | Optional model hint passed to both Worker and Evaluator turns.              |

The slash command is registered in
[`commands/manifests/goal.json`](../commands/manifests/goal.json) and the
behavior lives in [`blocks/goal/run.py`](../blocks/goal/run.py).

## Controller instruction layer

The Worker and Evaluator controller prompts are app-controlled instructions,
not ordinary user text. `/goal` sends them through the strongest
developer/instructions-equivalent request layer available to the selected
provider. When a provider only supports system messages, the model-call
materializer merges those developer instructions into a system-role fallback.

User goal text remains normal user content and is ordered below the controller
prompts, so goal text cannot override the Worker or Evaluator role contract.

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
      "stopped_reason": "achieved"
    }
  }
}
```

When the loop hits `max_iterations` without achieving the goal, `achieved`
becomes `false` and `stopped_reason` is `"max_iterations_reached"`. When the
Worker or Evaluator model call fails the command returns
`status: "error"` with `code: "WORKER_FAILED"` or `code: "EVALUATOR_FAILED"`
and an `iterations` array recording any partial progress.

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
