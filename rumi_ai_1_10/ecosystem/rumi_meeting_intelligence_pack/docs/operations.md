# Operations

## Reviewer Workflow

1. Confirm the source inventory is local and already available.
2. Choose the smallest preset that fits the task.
3. Extract only decisions, actions, risks, open questions, and follow-up drafts supported by evidence.
4. Mark unresolved owners, ambiguous deadlines, and missing source spans instead of guessing.
5. Produce a recap bundle with a human review gate and handoff queue.

## Quality Gates

- Decisions require source spans and confidence.
- Actions require owner, due date, dependency, or an explicit unknown marker.
- Follow-up drafts must be labelled `draft_only`.
- External execution must be represented as handoff, not completed work.
- Private attendee details should be redacted unless they are necessary to the meeting outcome.

## Failure Handling

If the supplied source is too thin, the correct output is an evidence gap report. If the task requires connector fetch, scheduling, live voice capture, business operations execution, or document parsing, stop and hand off to the correct owner pack.

Required Secrets: None.
