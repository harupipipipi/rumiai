<!-- docs-i18n-links:start -->
[EN](./ai_agent_services_comparison.md) | [JP](./i18n/ja/ai_agent_services_comparison.md) | [KR](./i18n/ko/ai_agent_services_comparison.md) | [CN](./i18n/zh-cn/ai_agent_services_comparison.md)
<!-- docs-i18n-links:end -->

# AI Agent Services Comparison

| Service | Local files | Terminal | Git | Plan | Approval | Memory | Projects | Artifacts | Research | Browser |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Codex | yes | yes | yes | yes | yes | session | repo | patch | optional | optional |
| Claude Code | yes | yes | yes | yes | yes | project | yes | files | optional | optional |
| ChatGPT Projects | partial | no | no | partial | n/a | yes | yes | yes | yes | no |
| Manus | yes | yes | partial | yes | yes | task | task | yes | yes | yes |
| Genspark | partial | partial | no | yes | partial | task | task | report | yes | yes |
| OpenClaw | yes | yes | yes | yes | yes | local | local | files | optional | optional |
| defaultspack target | yes | yes | yes | yes | yes | local | local | local | local-first | optional |

defaultspack adopts the local and extensible parts first. Cloud model APIs, web search, GitHub API, Reddit, and browser network access remain optional providers.
