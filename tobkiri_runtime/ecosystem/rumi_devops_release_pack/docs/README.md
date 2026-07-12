# Rumi DevOps Release Pack Docs

This directory contains pack-specific documentation for `rumi_devops_release_pack`.

## Reading Guide

- [architecture.md](architecture.md): responsibility boundaries, directory layout, runtime contact points, and execution path.
- [interfaces.md](interfaces.md): declared profiles, prompts, presets, catalogs, required secrets, network posture, grants, and overlap policy.
- [operations.md](operations.md): install expectations, development rules, test command, and common failure modes.

## First Pass

Read this pack as an operational evidence layer. It complements code and service packs by describing release gates, CI triage, deploy runbooks, and rollback planning. It does not execute deployments or fetch remote state on its own.
