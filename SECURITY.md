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

## Disclosure

The maintainer will aim to acknowledge valid reports promptly, investigate privately, and publish a fix before public disclosure when the impact warrants it.
