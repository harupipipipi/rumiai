# Security Policy

Rumi AI is a local-first AI runtime with pack, approval, capability, and audit boundaries. Security reports are welcome, especially when they involve bypassing local user approval, workspace isolation, secret handling, or host capability boundaries.

## Supported Versions

The public repository is currently pre-1.0 and fast-moving. Security fixes are handled on the default branch first.

## Reporting a Vulnerability

Please do not open a public issue for a vulnerability that can expose secrets, bypass approval, execute host commands, escape a workspace, or alter browser/computer/git behavior without user consent.

Use GitHub's private vulnerability reporting flow if it is enabled on the repository. If it is not enabled, contact the maintainer through the public GitHub profile and request a private reporting channel.

Include:

- A short impact summary.
- A minimal reproduction.
- Affected commit or release, if known.
- Whether secrets, files, terminal, browser, computer, git, network, or pack installation paths are involved.

## Security-Sensitive Areas

- Approval and grant flows.
- Capability trust and pack installation.
- Terminal, file write, git, browser, and computer-control paths.
- Secret storage and provider configuration.
- Workspace jail, path normalization, and archive extraction.
- Audit logging and tamper resistance.

## Maintainer Review Checklist

Use this checklist for any PR that touches security-sensitive paths:

- Does the change introduce a new write, terminal, git, browser, computer, network, or secret-handling path?
- Does every privileged path still require server-side approval, grant, or trust validation?
- Can a client-supplied flag, profile, pack, or request body bypass a local guard?
- Are paths normalized before filesystem access, archive extraction, or workspace boundary checks?
- Are secrets excluded from logs, screenshots, issue templates, traces, and audit payloads?
- Does the change preserve audit records for approval-sensitive behavior?
- Is there a focused regression test for the boundary being changed?
- If the behavior relies on platform APIs, has Windows/macOS/Linux behavior been considered separately?

If any answer is uncertain, keep the change small and request maintainer review before merging.

## Disclosure

The maintainer will aim to acknowledge valid reports promptly, investigate privately, and publish a fix before public disclosure when the impact warrants it.
