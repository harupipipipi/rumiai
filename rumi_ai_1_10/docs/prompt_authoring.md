# Prompt Authoring

Prompts need a stable prompt id, content, owner pack or profile, and lint/compaction expectations.

Pack prompts are defaults. Profile prompts in `profiles/<profile_id>/prompts/` override or extend pack defaults. Snapshot prompts under `ecosystem/snapshots/<pack>/prompts/` preserve the source version used when a profile was created.

Effective prompt priority is profile override, profile snapshot, then pack default. Prompt linting should flag redundancy, missing role context, and token budget risk. Compaction must preserve safety and tool-use constraints.
