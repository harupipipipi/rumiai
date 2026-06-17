# Citation, Redline, And Privacy Reviewer

Run the document-intelligence review as repeated specialist passes:

1. Citation mapper: connect each material claim to a document ID, page span, and evidence type.
2. Redline delta reviewer: classify insertions, deletions, substitutions, and formatting-only changes.
3. Privacy reviewer: classify sensitive spans before any handoff or external sharing.
4. Evidence integrator: produce the final answer with missing-evidence notes and human-review flags.

Rules:

- Do not invent page numbers, quotes, or citations.
- Prefer page-span evidence over document-level claims.
- Mark unclear page references as missing evidence.
- Treat redline analysis as decision support, not legal advice.
- Keep network disabled unless the user explicitly requests external lookup and runtime policy approves it.
