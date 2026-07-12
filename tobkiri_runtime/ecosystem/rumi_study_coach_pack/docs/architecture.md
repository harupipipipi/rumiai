# Architecture

Rumi Study Coach Pack is a setup pack, not a runtime service. It supplies the
contracts Rumi needs to produce study artifacts from already-available local
notes while keeping all external side effects outside this pack.

## Layers

1. Source boundary layer

   The pack consumes local note IDs, source spans, learner goals, constraints,
   and prior attempt summaries. It does not parse PDFs, scrape websites, query
   workspaces, or infer durable learner history. When those inputs are missing,
   the result is an uncertainty note or handoff request.

2. Study artifact layer

   The owned artifacts are learner profiles, study goals, diagnostics, study
   plans, practice sessions, review queues, progress reports, and
   evidence-bound explanations. Each schema requires source references or
   uncertainty fields so a reviewer can trace the output back to local notes.

3. Quality gate layer

   Workflows stay in `declarative_only` execution and pass through blocking
   gates for source note citation, no external fact invention, spacing reasons,
   difficulty calibration, accessibility constraints, and handoff owner naming.
   Failed gates return a blocked packet rather than a confident tutoring answer.

4. Handoff layer

   Owner packs handle adjacent runtime work: document intelligence parses
   notebooks, research fetches new background sources, memory stores durable
   learner state, workflow scheduler places reminders, and workspace exports
   study artifacts. This pack only prepares the reviewable packet that those
   owners can consume.

## Promotion Posture

This design keeps Rumi customizable without making defaultspack absorb every
specialized behavior. Defaultspack promotion remains false until maintainers
have evidence for cited quiz generation, uncertainty on thin notes, review
queue decay behavior, accessibility-aware planning, and scheduler handoffs.
