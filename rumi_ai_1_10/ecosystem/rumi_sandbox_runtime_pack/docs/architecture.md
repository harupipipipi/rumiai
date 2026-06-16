# Architecture

`rumi_sandbox_runtime_pack` separates intent, evidence, policy, and handoff.

1. Intent catalog classifies the workflow type.
2. Policy files state safety and ownership boundaries.
3. Profiles and prompts define the agent posture for this domain.
4. Presets and examples make common workflows repeatable.
5. Setup metadata exposes dependencies, overlaps, and defaultspack promotion criteria.

The architecture keeps Rumi modular: each pack owns one domain and routes overlapping work to the pack that owns that surface.
