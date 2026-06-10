<!-- docs-i18n-links:start -->
[EN](./system-mechanism.md) | [JP](../i18n/ja/concepts/system-mechanism.md) | [KR](../i18n/ko/concepts/system-mechanism.md) | [CN](../i18n/zh-cn/concepts/system-mechanism.md)
<!-- docs-i18n-links:end -->

# Runtime Mechanism (code-free version)

This document is organized so that you can follow "how Rumi AI works" without reading the code.

## 1. What happens at startup

1. `python -m rumi_ai` starts `rumi_ai_1_10/app.py`.
2. Kernel handlers are executed in the order of `flows/00_startup.flow.yaml`.
3. When security initialization, pack scan, and API server initialization are completed, `system.ready` will be issued.

The startup flow has four phases: `init -> security -> ecosystem -> finalize`.

## 2. Loading order of Flow and Modifier

Flows are loaded in the following order (higher priority):

1. `flows/` (Official)
2. `user_data/shared/flows/` (Sharing)
3. `ecosystem/<pack_id>/.../flows/` (provided by Pack)
4. `ecosystem/flows/` (compatible legacy)

Modifier is loaded in the same way and applies `inject_before / inject_after / append / replace / remove` to the target Flow.

## 3. Conditions for allowing Pack execution

Pack execution requires the following three steps:

1. **Approve**: Pack is approved
2. **Trust**: Approval hash and current hash must match
3. **Grant**: capability execution privilege is granted to principal

If any one of them is missing, it will not be executed. Packs with file changes are treated as `modified` and require re-approval.

## 4. Positioning of API server

- Kernel exposes an API in `127.0.0.1:8765`.
- This API is the gateway for pack management, flow execution, secrets, grants, desktop tokens, etc.
- Routes are extended by loading the Pack side `api_routes` in addition to the core API.

## 5. Relationship between viewer and runtime

`rumi_viewer` is a "shell that starts Kernel and connects to panel".

1. viewer resolves Python / venv / runtime path
2. Start Kernel with `python -m app`
3. Bootstrap to `/panel/` and display the UI

The independent frontend (`8766`) and panel (`8765/panel`) of `defaultspack` are separate conductors.

## 6. Pack distribution execution path (Import/Apply)

1. PackImporter stages and deploys zip/folder (Zip Slip/Bomb protection)
2. Validate ecosystem.json
3. PackApplier creates a backup and reflects it in `ecosystem/<pack_id>/`
4. After reflection, it will be treated as `modified`, so go to re-approval flow

## 7. Where can I read to dig deeper?

- Overall design: [../architecture.md](../architecture.md)
- Operation/API: [../operations.md](../operations.md)
- viewer launch path: [../rumi_viewer_start.md](../rumi_viewer_start.md)
- Pack development: [../pack-development.md](../pack-development.md)
