# Tobkiri Cloudflare Workers Python bridge

This deployable Worker exposes only:

- `GET /health`
- `POST /v1/tools/invoke` with `{"tool_name": "web_search", "arguments": {...}}`

Set `RUMI_CLOUDFLARE_WORKER_PYTHON_API_KEY` as a Wrangler secret on the
Worker, then set both `RUMI_CLOUDFLARE_WORKER_PYTHON_URL` and
`RUMI_CLOUDFLARE_WORKER_PYTHON_API_KEY` in the Tobkiri PackVM credential
environment.

The route contains fixed implementations for web search, Reddit search, and a
bounded arithmetic calculator. There is no `eval`, `exec`, shell,
`python_exec`, `sandbox_exec`, arbitrary module import, filesystem access, or
Cloudflare Sandbox/Container lifecycle. Browser, computer, local file, git,
terminal, desktop-session, and OAuth connector tools remain outside this
route.
