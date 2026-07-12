# Architecture

The pack has five declarative layers.

1. Intake classifies media type, source, rights, and privacy sensitivity.
2. Understanding extracts text, objects, layout, motion, or audio transcript cues.
3. Generation planning prepares prompts, negative constraints, dimensions, variants, and review criteria.
4. Review checks accessibility, brand fit, factual grounding, and visual defects.
5. Handoff sends approved assets or summaries to workspace, browser, or agent-service workflows.

No layer invokes a media provider directly. Provider selection and secrets remain with defaultspack and installed tools.
