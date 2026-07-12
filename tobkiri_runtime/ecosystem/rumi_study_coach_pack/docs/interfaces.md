# Interfaces

## Inputs

- Local artifacts supplied by the user or by an adjacent owner pack.
- Schema-bound records listed in `ecosystem.json`.
- Evidence IDs, source spans, and explicit uncertainty notes.
- Learner constraints such as deadline state, session length, explanation style,
  accessibility accommodations, and allowed source scope.
- Attempt summaries that are already present in the current packet.

Inputs must already be usable as local note records. If a caller supplies a raw
PDF, website, workspace file, or unresolved message thread, the study coach does
not parse or fetch it. It requests the owner pack first, then consumes the cited
result.

## Outputs

- Evidence-linked drafts for diagnostics, plans, quiz sessions, review queues,
  and progress reports.
- Review checklist results for all blocking quality gates.
- Handoff packets with owner pack, reason, artifact path, evidence IDs, and
  human-review requirement.
- Blocked packets when the request lacks local note evidence or attempts an
  external action.

Outputs may recommend next steps, but they do not perform them. A study plan may
describe review windows; the workflow scheduler owns reminders. A progress
report may describe export-ready content; the workspace pack owns export.

## Handoff Owners

- `rumi_document_intelligence_pack`: Parse notebooks, PDFs, and lecture
  material before this pack creates study artifacts.
- `rumi_research_pack`: Fetch new background sources only through a research owner; this pack consumes cited notes.
- `rumi_memory_knowledge_pack`: Persist durable learner memory outside the declarative study packet.
- `rumi_workflow_scheduler_pack`: Schedule review reminders after this pack emits review windows.
- `rumi_workspace_pack`: Export study sheets, slides, or flashcard tables through the workspace owner.

## Required Secrets

None.

## Does Not Provide

- document parsing
- web research
- long term memory storage
- calendar scheduling
- workspace export
- medical or therapeutic advice
- graded credential issuance

## Caller Contract

Callers should pass explicit local note IDs and should expect the pack to reject
uncited facts. If the request asks for a topic that is absent from the supplied
notes, the correct output is uncertainty plus a safe next step, not a generic
answer from background knowledge. If a request crosses a non-owner surface, the
correct output is a Handoff packet, not an attempted tool call.
