# First-Run Check

Use this page to verify that a fresh checkout can start the lightweight runtime path before trying the full viewer or pack workflows.

## 1. Install Runtime Dependencies

From the repository root:

```bash
python -m pip install --upgrade pip
pip install -r rumi_ai_1_10/requirements.txt
```

For development and tests:

```bash
pip install -r rumi_ai_1_10/requirements-dev.txt
```

## 2. Run Health Check

From the repository root:

```bash
python -m rumi_ai --health
```

If `just` is installed, this is equivalent:

```bash
just health
```

Expected shape:

```json
{
  "status": "UP",
  "timestamp": "...",
  "probes": {
    "disk": {
      "status": "UP"
    },
    "writable_tmp": {
      "status": "UP"
    }
  }
}
```

`DEGRADED` or `DOWN` can mean the system disk or temporary directory is unavailable or low on free space. Check the probe messages before assuming a code regression.

## 3. Run Entrypoint Contract Tests

```bash
python -m pytest tests/test_entrypoint_contracts.py -q
```

These tests keep the root `rumi_ai` entrypoint, version contract, and first-run docs aligned.

## 4. Verify OSS Readiness Materials

```bash
python scripts/verify_oss_readiness.py
```

If `just` is installed, this is equivalent:

```bash
just oss-readiness
```

This check is local only. It verifies that contribution, security, release, first-run, adoption-evidence, and application-draft materials are present before public outreach or program applications.

## 5. Next Steps

- Runtime architecture: `rumi_ai_1_10/README.md`
- Pack authoring: `rumi_ai_1_10/docs/pack-development.md`
- Viewer startup: `rumi_ai_1_10/docs/rumi_viewer_start.md`
- Community and release work: `docs/community-launch-plan.md`
