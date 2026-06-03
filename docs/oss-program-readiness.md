# OSS Program Readiness

This note tracks truthful evidence for OSS support programs such as Codex for Open Source and Claude for Open Source. It is not a substitute for the program terms. Keep the application honest and evidence-backed.

## Current Public Evidence

- Repository: `https://github.com/harupipipipi/rumiai`
- License: MIT
- Public activity: active pushes and PRs in June 2026
- Maintainer activity: commits, PR merges, and CI maintenance within the last three months
- CI coverage: Python, frontend, Rust, Windows, macOS, installer, and dependency-audit lanes
- Release artifacts: release workflow exists, but no public GitHub Releases were found during the June 3, 2026 review
- Discovery metadata: topics and homepage were empty during the June 3, 2026 review
- Adoption evidence: stars and forks are currently low; no public downstream dependency evidence was found during the June 3, 2026 review

## Eligibility Gap

Claude for Open Source Maintainer Track requires a public GitHub repository with at least 5,000 stars or 1M+ monthly NPM downloads, plus merge access and recent activity. Rumi AI does not currently meet the public usage threshold.

OpenAI Codex for Open Source is broader, but still asks for usage, adoption, ecosystem importance, and maintainer status. Rumi AI currently has stronger maintenance evidence than adoption evidence.

## 24-Hour Readiness Work

These tasks improve public credibility without inflating metrics:

- Add contribution and security policies.
- Add bug and feature issue templates.
- Improve README positioning for first-time users.
- Add repository topics and a concise GitHub description.
- Publish a first GitHub Release with installer artifacts or a source release.
- Create issues labeled `good first issue` for docs, examples, setup testing, and small pack examples.
- Add a short demo video or screenshots to the README or release notes.
- Publish a package only if the install path is tested and supportable.
- Collect real usage evidence: downstream repos, user installs, community links, articles, demos, or integrations.

See [community-launch-plan.md](./community-launch-plan.md) for concrete release notes, repository metadata, and issue drafts.

## Pull Request Draft

Title:

`docs: add OSS readiness and community launch materials`

Body:

```markdown
## Summary

- Add contributor, security, support, code-of-conduct, and issue-template materials for public OSS onboarding.
- Add an OSS program readiness note with truthful OpenAI/Claude application drafts and explicit anti-metric-inflation guidance.
- Add a community launch plan, first release notes draft, and draft-release workflow safety so the first public release can be reviewed before publishing.

## Impact

- Makes the repo easier for real users and contributors to evaluate.
- Gives maintainers concrete release, metadata, good-first-issue, and application copy to use.
- Keeps public claims honest about the current adoption gap.

## Validation

- [x] Parsed workflow and issue-template YAML locally.
- [x] Checked OpenAI application copy is under 500 characters per field.
- [x] Ran `git diff --check`.

## Security / Approval Notes

- [x] This change does not bypass local guard, approval, workspace jail, capability trust, or audit paths.
- [x] New write, terminal, git, browser, computer, or secret-handling behavior is approval-aware.
- [x] Release workflow now creates draft releases for review before public publishing.
```

## OpenAI Draft

Role:

Core maintainer / primary maintainer, if the applicant has write or admin access to `harupipipipi/rumiai`.

Why this repository should qualify (500 chars max):

Rumi AI is an actively maintained MIT-licensed local-first AI runtime for modular packs, approval-aware host capabilities, audit paths, and cross-surface AI tooling. It includes Python runtime code, a Tauri desktop viewer, Flutter mobile client, example packs, and CI for Python, frontend, Rust, Windows, macOS, installers, and dependency audits. Adoption is early; the strongest evidence is active maintenance and security-focused architecture.

API credit use (500 chars max):

API credits would support maintainer workflows: PR review, regression triage, release notes, security-oriented code review, documentation, and test generation around approval, pack installation, browser/computer control, terminal, git, and secret-handling paths. Credits would be used only for Rumi AI and authorized related maintenance, not to scan third-party repositories without permission.

Additional note (500 chars max):

Rumi AI is early-stage and does not yet have large public adoption metrics. I am applying on the strength of active maintenance, security-focused local-first architecture, and the project’s relevance to AI developer tooling. I am also improving public contribution, security, issue-template, release, and community onboarding materials.

## Claude Draft

Track:

Ecosystem Impact Track only, unless the repository reaches the published Maintainer Track threshold or the applicant becomes a maintainer of another qualifying project.

Explanation (Claude "Other info"):

Rumi AI is an MIT-licensed local-first AI runtime focused on modular packs, explicit approval boundaries, capability trust, auditability, and desktop/mobile surfaces for AI tooling. It is actively maintained with recent commits and PRs, includes CI coverage for Python, frontend, Rust, Windows, macOS, installer, and dependency-audit paths, and is designed around security-sensitive maintainer workflows. Current public adoption is limited, so this should be submitted under the discretionary Ecosystem Impact Track rather than the 5,000-star Maintainer Track.

## Do Not Do

- Do not buy stars, followers, installs, or reviews.
- Do not run star-for-star or follow-for-follow campaigns.
- Do not create fake accounts, fake users, fake dependents, or fake downloads.
- Do not claim ecosystem dependence without evidence.
- Do not submit another maintainer's repository without authorization.
- Do not submit forms with inaccurate role, access, adoption, or download claims.
