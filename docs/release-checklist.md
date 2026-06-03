# Release Checklist

This checklist keeps the first public release practical, reviewable, and easy for new users to test.

## Repository Metadata

Suggested GitHub description:

`Local-first modular AI runtime with approval-aware packs, audit trails, desktop viewer, and mobile client.`

Suggested topics:

- `ai`
- `ai-agents`
- `local-first`
- `developer-tools`
- `automation`
- `tauri`
- `flutter`
- `python`
- `security-tools`
- `open-source`

Suggested homepage:

Use a public docs or demo URL only after it exists. Leave blank until then.

## First Public Release

Target tag:

`v0.2.0`

Release title:

`Rumi AI v0.2.0 - local-first runtime preview`

Release notes draft:

Use [releases/v0.2.0.md](./releases/v0.2.0.md) as the base release notes.

Release checklist:

- Merge the release-readiness PR.
- Run `python scripts/verify_oss_readiness.py`.
- Run `python scripts/check_package_install.py`.
- Confirm CI is green on `master`.
- Create or update a changelog section.
- Tag `v0.2.0`.
- Let the release workflow produce draft release artifacts.
- Review generated artifacts and release notes.
- Publish the GitHub Release only after artifacts and notes are correct.
- Add a short screenshot or demo link if available.
- Ask first-time users to report setup results with the [setup feedback issue template](../.github/ISSUE_TEMPLATE/setup_feedback.yml).

## Good First Issue Backlog

Create these as public GitHub Issues after the release-readiness PR is merged.

### Improve first-run quickstart on Windows

Labels: `good first issue`, `documentation`, `windows`

Body:

```markdown
Try the root README quickstart on a fresh Windows machine and report any missing prerequisite, path, PowerShell, or encoding issue. Update the docs with the smallest fix.

Validation:

- `python -m rumi_ai --health` output is documented.
- `rumi-ai --health` output is documented.
- Any Windows-specific command differs from the Unix example only where needed.
```

### Add a minimal hello-world pack tutorial

Labels: `good first issue`, `documentation`, `packs`

Body:

```markdown
Add a small tutorial that creates a minimal pack, wires one route, and explains how approval/trust applies. Prefer an example that can be tested without network access or API keys.

Validation:

- Tutorial has copy-paste commands.
- No secrets or cloud accounts are required.
- The example names the approval boundary clearly.
```

### Add release screenshots

Labels: `good first issue`, `documentation`, `viewer`

Body:

```markdown
Add lightweight screenshots for the README or release notes showing the viewer home and defaultspack panel. Avoid screenshots that include API keys, private prompts, or personal data.

Validation:

- Images are optimized for GitHub rendering.
- README remains readable without images.
```

### Document security-sensitive contribution areas

Labels: `good first issue`, `security`, `documentation`

Body:

```markdown
Expand SECURITY.md with concise examples of changes that need extra review: approval/grant flow, terminal execution, file writes, git operations, browser/computer control, secrets, pack install, and workspace isolation.

Validation:

- No exploit details are published.
- The guidance helps contributors decide when to ask for maintainer review.
```

## Evidence To Collect

- Public releases and artifact download counts.
- Setup feedback issues with OS, commands tried, and health-check output.
- Real issues and PRs from users who tried the project.
- Downstream repos or packs that depend on Rumi AI.
- Articles, demos, videos, or community threads with real discussion.
- Package downloads only if packages are published and supportable.

Track evidence in [user-feedback-evidence.md](./user-feedback-evidence.md). Keep it public-link based where possible and avoid private user data.

## Boundaries

- Do not buy stars, follows, downloads, reviews, or installs.
- Do not run star-for-star or follow-for-follow campaigns.
- Do not create fake accounts, fake users, fake dependent packages, or fake testimonials.
- Keep feedback collection in GitHub issues, PRs, and release comments.
- Do not post repetitive messages into unrelated communities.
- Do not claim adoption metrics without evidence.
