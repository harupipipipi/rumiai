# ADR 0001: Pack Boundary Assessment Criteria

- Status: Draft
- Decision scope: architecture review only
- Runtime authority: none
- Activation input: no

## Context

The current repository contains many directories represented as Packs. A directory
boundary is useful for organization, but it does not by itself prove that the
directory should be a separately installable, independently trusted runtime unit.
Treating the current topology as canonical would turn implementation history into
a public extension contract before ownership and isolation have been reviewed.

## Decision

We will keep a repository-level assessment of every runtime Pack manifest. The
assessment is evidence for a later architecture decision. It is not read by the
runtime, does not participate in activation or approval, and is not included in a
Pack signature or trust decision.

A Pack boundary is justified only when the review finds one or more substantive
reasons for it:

1. It has an independent release, upgrade, rollback, or deprecation lifecycle.
2. It crosses a distinct trust or authority boundary.
3. Process, VM, or fault isolation has meaningful security or reliability value.
4. It owns independently migrated durable state.
5. A third party can genuinely replace or distribute it independently.

A normal internal responsibility split, an import boundary, or a UI section is
not sufficient by itself. Such code may ultimately be a module or resource inside
a larger Pack.

Unknown values remain explicit until evidence exists. An assessment row cannot be
accepted while its lifecycle owner, state owner, trust domain, execution mode,
canonical owner, or disposition remains unresolved.

## Inventory contract

`docs/status/pack-boundary-assessment.v1.json` records the observed manifests and
their unresolved review state. `scripts/quality/check_pack_boundary_assessment.py`
checks that every production Pack manifest appears exactly once and that stale rows
are removed. It also rejects any production Python reference to the assessment.

Adding, removing, or moving a Pack manifest therefore creates review drift without
making the assessment an executable catalog.

## Consequences

- Existing Packs continue to load exactly as before.
- No `ecosystem.json` file changes and no approval hash is invalidated.
- The present topology, including any larger experimental v4 catalog, is not
  declared standard, canonical, or a supported third-party API by this ADR.
- Consolidation, compatibility aliases, and deletion require later accepted
  decisions with migration evidence.
