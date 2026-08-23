# Cloudflare Workers Python fixed-tool Pack

This optional Pack provides signed fixed-tool definitions plus one exact
`tobkiri.service.tool.remote.operation.v1` provider for Workers-Python-
compatible tools. The definitions seal the remote provider identity; callers
cannot select or override an execution route. Both operations run through the
PackVM boundary.

The Pack is intentionally absent from the default Profile. An explicit
Profile must include it together with the complete v4 tool broker, registry,
selector, remote executor, policy, authorization, and audit graph. This keeps
Worker credentials optional and prevents legacy or host fallback.

Configure the PackVM environment with:

- `RUMI_CLOUDFLARE_WORKER_PYTHON_URL`
- `RUMI_CLOUDFLARE_WORKER_PYTHON_API_KEY`

The runtime accepts only `web_search`, `reddit_search`, `calculator`, and the
two finite search aliases. It has no Python eval/exec, shell, filesystem,
browser-session, desktop, OAuth-connector, or host-execution fallback.
