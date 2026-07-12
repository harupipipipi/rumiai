# Rumi Security Review Pack Docs

This directory contains pack-specific documentation for `rumi_security_review_pack`.

## Reading Guide

- [architecture.md](architecture.md): responsibilities, directory layout, execution model, and runtime boundaries.
- [interfaces.md](interfaces.md): catalogs, profiles, prompts, presets, examples, secrets, network, grants, and overlap behavior.
- [operations.md](operations.md): installation, development, test commands, failure modes, and review checklist.

## First-Time Orientation

This pack is a declarative security review layer. It helps reviewers reason about Rumi-native risks, but enforcement remains with defaultspack, runtime policy, grant stores, approval flows, and owner packs such as MCP gateway or browser packs.
