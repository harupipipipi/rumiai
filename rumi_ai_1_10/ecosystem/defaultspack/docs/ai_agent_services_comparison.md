# AI Agent Services Comparison

| Service style | Local files | Terminal | Git | Browser | Research | Artifacts | Memory | Compact | Approval |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Codex-like | yes | yes | yes | optional | limited | code/docs | project | yes | yes |
| Claude Code-like | yes | yes | yes | optional | limited | code/docs | project | yes | yes |
| ChatGPT Projects-like | project files | optional | optional | optional | optional | yes | user/project | summary | yes |
| Manus-like | yes | optional | optional | yes | yes | deliverables | task | step log | yes |
| Genspark-like | optional | no | no | yes | yes | reports/pages | limited | report | source review |
| OpenClaw-like | yes | yes | yes | optional | optional | custom | local | optional | policy |

defaultspack keeps API-dependent behavior outside core by using provider manifests, tool manifests, and capability approval policy.
