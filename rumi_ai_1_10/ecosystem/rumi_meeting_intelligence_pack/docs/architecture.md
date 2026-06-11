# Architecture

The pack is a declarative layer over existing local meeting artifacts. It turns supplied notes and transcripts into structured analysis bundles, but it does not own the systems that capture, parse, transmit, or execute meeting work.

## Flow

1. Source inventory identifies local transcript, agenda, notes, chat export, or already extracted document text.
2. Meeting prep uses only supplied material to produce goals, likely decisions, open questions, risks, and stakeholder context.
3. Transcript review creates decision records, action records, open questions, and unresolved conflicts.
4. Evidence linking attaches each claim to a source id, span, excerpt summary, and confidence value.
5. Follow-up drafting produces message drafts and handoff records, never external sends.
6. Recap bundling packages the summary, decision log, action register, evidence ledger, and owner handoff queue.

## Local Runtime Shape

The pack has no functions, routes, stores, or executable components. It is designed to be read by defaultspack and adjacent owner packs as a contract for analysis behavior and quality gates.

## Boundary Model

The pack owns analysis and drafting. It hands off:

- remote context retrieval to connector owners,
- timed work to scheduler owners,
- voice and transcription to voice/mobile owners,
- CRM, ticket, project, and outbound execution to business operations owners,
- document parsing and conversion to document intelligence owners.
