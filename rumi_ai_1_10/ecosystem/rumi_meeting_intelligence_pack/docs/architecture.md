# Architecture

`rumi_meeting_intelligence_pack` is declarative. It ships catalogs, schemas, policies, templates, examples, prompts, profiles, and presets. It registers no tools and grants no broad permissions.

Owned surfaces: meeting_prebrief, decision_log, action_item_extraction, evidence_linked_recap, followup_draft_contract.

The primary artifact is an evidence-linked recap bundle. It contains source evidence, transcript-to-decision records, action items, draft follow-ups, open questions, and an owner handoff queue. The bundle is useful without network or secrets, and any request to fetch, send, schedule, parse, capture, or update external systems must leave this pack as a handoff.
