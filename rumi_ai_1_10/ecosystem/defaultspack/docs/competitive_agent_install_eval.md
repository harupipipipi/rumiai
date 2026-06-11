<!-- docs-i18n-links:start -->
[EN](./competitive_agent_install_eval.md) | [JP](./i18n/ja/competitive_agent_install_eval.md) | [KR](./i18n/ko/competitive_agent_install_eval.md) | [CN](./i18n/zh-cn/competitive_agent_install_eval.md)
<!-- docs-i18n-links:end -->

# Competitive Agent Install Evaluation

Date: 2026-06-03

This note records the defaultspack install/onboarding checks run against the
current public install flows for Genspark, Manus, Cline, Hermes, and OpenClaw.
It is intended to keep defaultspack competitive with browser-first and
agent-runtime products without weakening the local-first security model.

## Tested Flows

| Product | Install or launch path observed | Practical bar defaultspack must meet |
| --- | --- | --- |
| Genspark | Browser workspace at `https://www.genspark.ai/ja`, with visible Claw, workflow, drive, and app entry points. | A first screen must make chat, tools, workspace, and settings discoverable without reading docs. |
| Manus | Browser app at `https://manus.im/app`. | The app shell must load from one URL and tolerate auth-gated or empty initial state. |
| Cline | Official install docs show IDE extension, CLI, Kanban, and SDK paths. IDE install is: open extensions, search Cline, install, open activity bar, then authorize provider. CLI install is `npm install -g cline`, `cline auth`, then `cline`. | defaultspack must support both UI-first and command-first setup, and provider setup must be explicit after install. |
| Hermes | `NousResearch/hermes-agent` GitHub page exposes a large agent runtime with installer, desktop build, gateway, providers, plugins, skills, and dashboard surfaces. | defaultspack needs visible provider, tool, approval, and dashboard primitives rather than only raw chat. |
| OpenClaw | Official docs provide installer scripts, npm install, onboarding, gateway status, dashboard launch, and channel setup. Windows installer is `iwr -useb https://openclaw.ai/install.ps1 | iex`; no-onboard mode is also documented. | defaultspack needs a short install path, a no-network/no-key local mode, and clear next-step checks for gateway/UI/model status. |

## defaultspack Results

- `python -m rumi_ai --health` returned `UP` for disk and writable temp probes.
- `npm test` in `ecosystem/defaultspack/webapp` passed 207 tests.
- `npm run build` produced the production shell assets.
- Chrome opened the dev UI at `http://127.0.0.1:39766/` and rendered the
  defaultspack luxe shell.
- `npm run lint` initially failed on Windows because lint scripts used
  `new URL(...).pathname`, producing `C:\C:\...`; this was fixed with
  `fileURLToPath(import.meta.url)`.

## Competitor Local Install Notes

- `npm install --prefix work/competitor-installs/cline cline@3.0.15` completed,
  and `cline --help` showed provider auth, local data-dir, worktree, hooks, MCP,
  hub, scheduler, and Kanban commands.
- `npm install --prefix work/competitor-installs/hermes --ignore-scripts
  hermes-agent@0.15.2` completed, but `hermes-agent --help` failed with
  `ModuleNotFoundError: No module named 'run_agent'` in this Windows environment.
- `npm install --prefix work/competitor-installs/openclaw openclaw@2026.5.28`
  exceeded five minutes while postinstall/health processes were still running.
  A second `--ignore-scripts` attempt also exceeded three minutes. This makes
  OpenClaw's installer attractive when it works, but its package install is a
  heavier operational path than defaultspack's local-first start.

## OpenCode Zen Check

- Direct Python/urllib access to `https://opencode.ai/zen/go/v1/models` was
  blocked by Cloudflare Error 1010 in this environment.
- Chrome-channel API access with the supplied Zen key returned the current model
  list, including `minimax-m3` and `qwen3.7-max`.
- A live completion attempt for `minimax-m3` reached OpenCode but returned a
  `CreditsError` because the workspace has no payment method configured.
- defaultspack now includes `opencode-go/minimax-m3` and
  `opencode-go/qwen3.7-max` in both the Python provider allowlist and static
  provider model catalog.

## Competitive Readiness Checklist

- Local-first start without cloud keys.
- Visible UI shell from one localhost URL.
- Provider key setup after install, not during clone/build.
- Model catalog includes current OpenCode Zen models used by evaluators.
- Browser/computer/tool approvals remain explicit and auditable.
- Windows lint/build path works on absolute workspace paths.
- Install evidence is reproducible from health, unit, lint, build, and Chrome
  smoke checks.
