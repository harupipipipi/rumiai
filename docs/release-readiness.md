# Release Readiness

This note tracks practical release and maintenance readiness for Rumi AI. Keep it truthful, reproducible, and useful for maintainers, contributors, and first-time users.

## Current State

- Repository: `https://github.com/harupipipipi/rumiai`
- License: MIT
- Public activity: active pushes and PRs in June 2026
- Maintainer activity: commits, PR merges, and CI maintenance within the last three months
- CI coverage: Python, frontend, Rust, Windows, macOS, installer, and dependency-audit lanes
- Release artifacts: release workflow exists and creates draft releases for maintainer review
- Packaging: root editable install and wheel smoke checks are available

## Near-Term Work

These tasks improve public usability without inflating metrics or making claims that are not yet backed by evidence:

- Keep contribution and security policies visible.
- Keep bug, feature, and setup-feedback issue templates clear.
- Keep the README focused on first-run success.
- Keep `python -m rumi_ai --health` and `rumi-ai --health` working outside the checkout after installation.
- Keep `scripts/check_package_install.py` passing before publishing releases.
- Publish a first GitHub Release only after generated artifacts and notes are reviewed.
- Create small issues labeled `good first issue` for docs, examples, setup testing, and small pack examples.
- Publish packages only when the install path is tested and supportable.
- Track real setup reports, downstream use, issues, PRs, and maintainer responses with public links.

See [release-checklist.md](./release-checklist.md) for release notes, repository metadata, and issue drafts.
See [user-feedback-evidence.md](./user-feedback-evidence.md) for a truthful feedback and usage evidence tracker.

## Pull Request Draft

Title:

`docs: improve public release and contributor readiness`

Body:

```markdown
## Summary

- Add contributor, security, support, code-of-conduct, and issue-template materials for public OSS onboarding.
- Add first-run, release-readiness, and feedback-evidence docs so setup results and real usage can be tracked without inflating metrics.
- Add a release checklist, first release notes draft, and draft-release workflow safety so generated release artifacts can be reviewed before publishing.
- Add root package metadata, console entrypoints, and package smoke checks for installed runtime health checks outside the repository checkout.

## Impact

- Makes the repo easier for real users and contributors to evaluate.
- Makes the first-run path installable from the repository root and testable outside the checkout.
- Gives maintainers concrete release, metadata, good-first-issue, and validation guidance.
- Adds a place to record public feedback, downstream use, and setup results.
- Keeps public claims honest about the current early state.

## Validation

- [x] Parsed workflow and issue-template YAML locally.
- [x] Ran `python scripts/verify_oss_readiness.py`.
- [x] Ran `python scripts/check_package_install.py`.
- [x] Verified a fresh virtualenv can run `pip install -e .`, then `python -m rumi_ai --health` from outside the checkout.
- [x] Verified a built wheel can be installed into a fresh virtualenv and run both `python -m rumi_ai --health` and `rumi-ai --health`.
- [x] Ran `git diff --check`.

## Security / Approval Notes

- [x] This change does not bypass local guard, approval, workspace jail, capability trust, or audit paths.
- [x] New write, terminal, git, browser, computer, or secret-handling behavior is approval-aware.
- [x] Release workflow creates draft releases for review before public publishing.
```

## Boundaries

- Do not buy stars, followers, installs, reviews, or downloads.
- Do not run star-for-star or follow-for-follow campaigns.
- Do not create fake accounts, fake users, fake dependents, fake testimonials, or fake downloads.
- Keep feedback collection in GitHub issues, PRs, and release comments.
- Do not claim downstream use, users, releases, or package adoption without public evidence.
- Do not represent another repository, package, maintainer, or organization without authorization.
