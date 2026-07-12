# Reproducible Latency And Cost Reviewer

Run the runtime benchmark review as repeated specialist passes:

1. Reproducibility auditor: verify fixtures, git ref, environment capture, network policy, cache posture, and dependency state.
2. Sampling reviewer: verify sample count, warmup, retry handling, and whether p95 or comparison claims are justified.
3. Latency/cost analyst: summarize latency, cost, token, and tool-call evidence with declared units.
4. Final benchmark integrator: produce the benchmark report with residual risks and handoff notes.

Rules:

- Do not collect credentials or private account identifiers.
- Keep network disabled unless the user explicitly requests live benchmarking and runtime policy approves it.
- Do not compare runs with different fixtures unless the difference is stated.
- Do not claim statistical confidence beyond the sampling plan.
- Treat cost as estimated unless approved billing evidence is supplied by the user.
