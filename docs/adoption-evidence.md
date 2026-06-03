# Adoption Evidence

Use this file to collect truthful public evidence for OSS support programs, release planning, and maintainer prioritization.

Do not add private user data, private emails, API keys, tokens, unpublished customer names, private prompts, proprietary logs, or confidential usage numbers.

## Current Snapshot

Last reviewed: June 3, 2026

- GitHub stars: 5
- Forks: 0
- Public releases: none
- Public packages: none
- Known downstream dependents: none verified
- Known external users: none verified
- Known public demos/articles: none verified

## Evidence Categories

### Public Releases

| Date | Version | Link | Artifacts | Notes |
|---|---|---|---|---|
| TBD | `v0.2.0` | TBD | TBD | First draft release target |

### Real User Reports

| Date | Source | User / org | Evidence link | What they tried | Outcome |
|---|---|---|---|---|---|
| TBD | GitHub Issue / Discussion / external post | TBD | TBD | TBD | TBD |

Preferred first-run reports should use the [setup feedback issue template](../.github/ISSUE_TEMPLATE/setup_feedback.yml). Count both successful and failed setup reports when they include a public link, environment, commands tried, and a clear outcome.

### Downstream Use

| Date | Project | Link | Integration type | Maintainer-confirmed? | Notes |
|---|---|---|---|---|---|
| TBD | TBD | TBD | Pack / runtime / viewer / docs | TBD | TBD |

### Public Mentions

| Date | Source | Link | Summary | Follow-up |
|---|---|---|---|---|
| TBD | Blog / video / social / forum | TBD | TBD | TBD |

### Community Feedback

| Date | Channel | Link | Feedback | Action taken |
|---|---|---|---|---|
| TBD | GitHub Issue / PR / Discussion | TBD | TBD | TBD |

## Evidence Quality Rules

Strong evidence:

- Public links to issues, PRs, releases, downstream repositories, articles, talks, videos, or package statistics.
- Maintainer-confirmed downstream usage.
- Reproducible demos with exact commands and version numbers.
- User reports that include environment, command output, and outcome.

Weak evidence:

- Private claims that cannot be shared or verified.
- One-off messages without project or user context.
- Page views, impressions, or likes without evidence that anyone tried the project.
- Stars or follows without usage context.

Do not count:

- Bought stars, bought downloads, star-for-star campaigns, follow exchanges, fake accounts, fake dependents, or generated testimonials.
- Private usage numbers that the user or organization did not authorize for publication.
- Any repository, package, or system the maintainer is not authorized to represent.

## Outreach Copy Drafts

Use these only in communities where Rumi AI is relevant and where self-promotion is allowed.

Short release post:

```text
Rumi AI is an early MIT-licensed local-first runtime for modular AI tools: pack-based architecture, approval-aware host capabilities, audit paths, a Tauri viewer, and a Flutter mobile client. I am preparing the first public release and would value setup feedback from people interested in local-first AI developer tooling.
```

Feedback request:

```text
I am looking for concrete setup feedback on Rumi AI. The smallest useful test is cloning the repo, installing the runtime requirements, and running `python -m rumi_ai --health`. If it fails, please share OS/runtime versions and the smallest log excerpt with secrets removed.
```

Issue-based feedback request:

```text
I added a setup feedback issue template for Rumi AI. If you are willing to try the first-run check, please run `python -m rumi_ai --health` and file the outcome here: https://github.com/harupipipipi/rumiai/issues/new?template=setup_feedback.yml
```

Security-review request:

```text
Rumi AI is designed around approval-aware execution for packs, files, terminal, git, browser/computer control, and secrets. I would appreciate review from people interested in local-first AI runtime boundaries. Please use private vulnerability reporting for anything that looks like an approval or secret-handling bypass.
```
