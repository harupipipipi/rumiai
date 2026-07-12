---
name: rumi-ui-candidate-judge
description: Judge Rumi UI foundation, leaf, and page candidates for acceptance. Use when comparing generated candidates, enforcing hard-fail rules, measuring compression, rejecting unsafe or unverified bundles, and writing or recommending accepted bundle manifests.
---

# Rumi UI Candidate Judge

Use this skill to decide whether a Rumi UI candidate can become an accepted bundle.

Read `references/judging-rubric.md` before judging. Fail closed when evidence is missing.

## Workflow

1. Identify the candidate kind: foundation, leaf, or composed page.
2. Load the relevant contract, plan config, accepted foundation, and candidate manifest.
3. Verify build/runtime health and required scenarios, viewports, and text scales.
4. Apply hard-fail rules first.
5. Apply compression scoring only after hard fails are cleared.
6. Accept exactly one candidate per `runId` and `nodeId`, or reject all with actionable reasons.

## Output

For acceptance, record the accepted candidate id, source contract, foundation ref, scenario coverage, verification evidence, and any import paths needed by the page composer. For rejection, list hard-fail codes first, then compression notes and regeneration guidance.

Do not accept unverified work, arbitrary tokens, primary truncation, horizontal overflow, or candidates that require page composer edits to their internals.
