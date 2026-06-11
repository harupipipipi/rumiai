# Interfaces

## Inputs

Accepted inputs are existing user-supplied materials:

- transcript text with speaker labels or line numbers,
- agenda or meeting brief text,
- local notes,
- chat or email excerpts already provided by the user,
- already extracted document text.

The pack must not fetch calendars, pull mail, download drive files, join meetings, record audio, or parse binary documents. Those actions require an explicit handoff to another owner pack.

## Outputs

The pack emits draft and bundle artifacts:

- meeting prep brief,
- decision log,
- action register,
- open question list,
- follow-up drafts,
- evidence-linked recap bundle,
- owner handoff queue.

## Evidence References

Every material claim must include an evidence reference with:

- `source_id`,
- `source_type`,
- `source_span`,
- `excerpt_summary`,
- `confidence`,
- `claim_ids`.

## Handoff Records

Execution requests must be represented as handoff records with the owner pack, requested action, review status, and evidence references. No handoff record is itself permission to send, schedule, update, or publish.

Required Secrets: None.
