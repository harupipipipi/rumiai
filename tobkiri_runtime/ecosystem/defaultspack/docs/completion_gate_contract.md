# Completion-gate runtime contract

Completion gates are pack-owned checks that run after `AgentEngine` produces a
candidate response and before that response becomes final. The engine resolves
gates only through the global registry; it does not import the owning feature or
pack.

## Registration

```python
from domain.agent_runtime import register_completion_gate


def review_candidate(request):
    if request["candidate"] == "ready":
        return {"verdict": "pass", "summary": "ready"}
    return {
        "verdict": "revise",
        "summary": "missing verification",
        "instruction": "run the focused verification and cite its receipt",
        "evidence": [],
        "required_user_action": None,
        "metadata": {"resolved_model": "reviewer/model"},
    }


register_completion_gate("example.quality", review_candidate)
```

Handlers receive `tobkiri.completion_gate.v1` requests containing the run ID,
ordered gate index, attempt and revision iteration, stable idempotency key,
candidate, durable step receipts, resolved run model, principal, and any evidence
supplied when a blocked gate is resumed. Implementations that delegate to an
agent or model must do so through the normal runtime, so tool policy, workspace
trust, sandboxing, and Authority remain in force.

The stable idempotency key must be honored by implementations that perform
external work. A delivery may be repeated after a process failure that occurs
after external work but before its verdict is durably recorded.

## Run policy

Attach ordered IDs directly to a run, its `run_policy`, or its selected
`runtime_profile`:

```json
{
  "completion_gates": ["example.quality", "example.policy"],
  "completion_gate_policy": {
    "max_iterations": 3,
    "max_attempts_per_gate": 2,
    "timeout_seconds": 30,
    "max_wall_clock_seconds": 300,
    "stagnation_limit": 2,
    "failure_mode": "blocked"
  }
}
```

Gate order is deterministic. Duplicate IDs are rejected as a cycle. Every
revision restarts the ordered chain against the new candidate. Iteration,
attempt, wall-clock, timeout, and repeated-instruction stagnation budgets are
policy values rather than feature constants.

Unknown or disabled IDs, invalid policies, malformed verdicts, timeouts, and
provider failures never pass implicitly. `failure_mode` chooses whether those
closed failures leave the run `blocked` for operator review or terminally
`failed`.

## Verdicts and lifecycle

- `pass` advances to the next gate. The original candidate remains unchanged.
- `revise` requires a non-empty instruction, injects it as a new message, and
  resumes model execution under the same run ID and approval state.
- `blocked` preserves the candidate and `required_user_action` until
`AgentEngine.resume_completion_gate()` is called with new evidence.

Resume evidence is an untrusted hint. A gate that waits for Authority must
resolve and verify the referenced Authority request through the normal runtime;
the gate's own principal or model output cannot approve that request.

A gate may return `transformed_result` only if its registry entry explicitly
sets `allow_transformed_result=True`. This keeps ordinary reviewers from
silently replacing the candidate.

The durable event stream records `candidate_complete`, attempt start/failure,
verdict, revision, blocked/failed terminal reason, cancellation, resume evidence,
and final completion. Verdict records include gate ID, attempt, iteration,
evidence, instruction, resolved model, metadata, and idempotency key.

Cancellation is rechecked after delivery, so a concurrent cancel wins over a
late `pass` or `revise`. A restart reconstructs the candidate and gate state from
the run store; blocked and in-flight runs can be resumed without creating a new
execution.
