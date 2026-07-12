# Rumi Study Coach Pack

Declarative local-note study coaching, diagnostic assessment, quiz generation,
spaced review, and progress reporting pack.

This pack is local-first, declarative, and designed as a customization layer for
Rumi. It adds domain-specific contracts, workflows, schemas, review gates, and
handoff packets without adding executable runtime code. The pack should be read
as a bounded tutoring contract: it can turn already-available notes into study
artifacts, but it cannot fetch, parse, store, schedule, export, or certify
anything on its own.

## Provides

- learner_profile
- study_goal_contract
- diagnostic_assessment
- study_plan
- practice_session
- quiz_item_contract
- spaced_review_queue
- progress_report
- evidence_bound_explanation

## Does Not Provide

- document parsing
- web research
- long term memory storage
- calendar scheduling
- workspace export
- medical or therapeutic advice
- graded credential issuance

## Required Secrets

None. The pack declares no credential requirement and no network access by
default. Any workflow that asks for credentials, connector state, browser
sessions, calendar writes, cloud storage, or durable learner memory is outside
this pack and must become a handoff packet.

## Evidence Contract

Every generated answer, quiz item, plan step, review queue item, and mastery
estimate must cite local `source_note_ids` or explicit span IDs. If the notes do
not support the requested claim, the pack records uncertainty and a safe next
step instead of supplying outside facts. A study artifact is not review-ready
until it includes:

- a declared learner goal and success criteria
- local note IDs or evidence IDs for each claim
- uncertainty notes for missing, thin, or conflicting evidence
- the owner pack for every adjacent runtime action
- a human-review state before any handoff leaves the pack

## Defaultspack Promotion

Not eligible by default. Promotion requires the blockers below to be cleared
with maintainer-reviewed evidence:

- requires_user_learning_goals
- requires_local_note_evidence
- scheduling_owned_by_workflow_scheduler_pack
- memory_storage_owned_by_rumi_memory_knowledge_pack
- must_prove_uncertainty_when_notes_are_insufficient

Promotion evidence must include cited quiz cases, insufficient-note uncertainty
cases, review queue decay cases, learner accommodation cases, and scheduler
handoff cases. Until those receipts exist, this pack stays separate from
defaultspack and `supports_all_ok` remains false.

## Handoff Model

The pack uses defaultspack as the base and hands adjacent runtime actions to
explicit owner packs. If another pack overlaps, the narrower owner surface wins
and this pack emits a reviewable handoff packet. Typical handoffs are:

- parsed notebook/PDF material to `rumi_document_intelligence_pack`
- fresh source gathering to `rumi_research_pack`
- durable learner memory to `rumi_memory_knowledge_pack`
- reminders and calendar placement to `rumi_workflow_scheduler_pack`
- study sheet, slide, or table export to `rumi_workspace_pack`

The handoff packet must name the owner, reason, evidence IDs, artifact path, and
human-review requirement. This keeps the study coach useful without letting it
silently take over document parsing, research, memory, scheduling, or workspace
export responsibilities.
