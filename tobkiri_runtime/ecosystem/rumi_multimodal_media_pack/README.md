# Rumi Multimodal Media Pack

Rumi Multimodal Media Pack organizes image, screenshot, OCR, audio, video, and visual QA work into local-first workflows. It is meant for tasks like reading screenshots, preparing image briefs, reviewing generated assets, comparing UI captures, creating accessibility notes, and handing polished media artifacts to workspace workflows.

The pack does not ship a model provider or media generation engine. It defines prompts, ledgers, review contracts, and handoffs so media work remains auditable and compatible with defaultspack grants.

## Required Secrets

None.

## Overlap Policy

- `defaultspack` owns provider keys, grants, and audit surfaces.
- `rumi_workspace_pack` owns final slide, sheet, doc, and PDF packaging.
- `rumi_browser_element_pack` can provide screenshots and page evidence for visual QA.
- This pack owns media asset ledgers, OCR review contracts, and visual quality checklists.
