# Rumi Study Coach Pack Docs

Read these docs before enabling `rumi_study_coach_pack` in a Rumi profile. The
pack is intentionally declarative: it defines contracts, review gates, and
handoff packets for study coaching, but it does not execute tools or mutate
external state.

## Reading Order

1. `architecture.md` explains the local-note pipeline and why adjacent runtime
   actions stay with their owner packs.
2. `interfaces.md` defines the inputs, outputs, handoff owners, and non-owner
   boundaries that callers must preserve.
3. `operations.md` gives maintainer checks for enablement, failure handling,
   promotion review, and evidence audits.

## Review Focus

The most important review question is whether an artifact is evidence-bound. A
valid study artifact names local notes or span IDs for every claim, names
uncertainty when notes are insufficient, and emits a Handoff packet instead of
performing document parsing, research, memory storage, scheduling, or workspace
export.

## Required Secrets

None. This pack must remain usable without credentials, network access, host
execution, or connector state.
