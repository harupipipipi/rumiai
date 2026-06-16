# Rumi Workflow Scheduler Pack Docs

This directory contains pack-specific documentation for `rumi_workflow_scheduler_pack`.

## Reading Guide

- [architecture.md](architecture.md): responsibilities, directory layout, execution model, and runtime boundaries.
- [interfaces.md](interfaces.md): catalogs, policies, profiles, prompts, presets, examples, secrets, network, grants, and overlap behavior.
- [operations.md](operations.md): installation, development, test commands, failure modes, and review checklist.

## First-Time Orientation

This pack defines scheduling contracts rather than running schedules. A Rumi surface can use these assets to shape recurring tasks, monitors, wakeups, follow-ups, and delivery handoffs, then route real execution to the app automation tool or defaultspack scheduler when those are available and approved.
