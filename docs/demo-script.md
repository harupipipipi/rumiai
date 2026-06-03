# Demo Script

Use this script for a short release video, social post, or issue-based feedback request. Keep the demo honest: show the current early state, do not claim large adoption, and remove secrets from the screen.

## Goal

Show that a fresh checkout can run the lightweight health path and that the project has clear security and contribution boundaries.

## Setup

```bash
git clone https://github.com/harupipipipi/rumiai.git
cd rumiai
python -m pip install --upgrade pip
pip install -e .
```

## Demo Flow

1. Show the repository README and point to `docs/first-run-check.md`.
2. Run:

   ```bash
   python -m rumi_ai --health
   rumi-ai --health
   ```

3. Show the `status: UP` JSON shape.
4. Run:

   ```bash
   python scripts/verify_oss_readiness.py
   ```

5. Show `status: pass`.
6. Open `SECURITY.md` and highlight the maintainer review checklist.
7. Open `docs/adoption-evidence.md` and explain that real usage evidence is tracked with public links, not inflated metrics.

## 60-Second Voiceover

```text
Rumi AI is an early MIT-licensed local-first runtime for modular AI tooling. The smallest check is a fresh clone plus `python -m rumi_ai --health`, which verifies disk and temporary-directory readiness without requiring API keys. The project is built around pack boundaries, approval-aware host capabilities, and auditability. I am looking for concrete setup feedback, security review, and small example-pack contributions. Public adoption is still early, so feedback and downstream use are tracked with public evidence rather than inflated metrics.
```

## What Not To Show

- API keys, tokens, private prompts, local usernames, email inboxes, private repos, or personal files.
- Claims about users, downloads, dependents, or stars without public evidence.
- Security exploit details that should go through private vulnerability reporting.
