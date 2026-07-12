# Rumi MCP Gateway Pack Docs

This directory contains pack-specific documentation for `rumi_mcp_gateway_pack`.

## Reading Guide

- [architecture.md](architecture.md): responsibilities, directory layout, runtime boundaries, and how unknown MCP servers are represented.
- [interfaces.md](interfaces.md): catalogs, templates, policies, dependencies, grants, network, secrets, and overlap with `defaultspack`.
- [operations.md](operations.md): installation, development, test expectations, and common failure modes.

## First-Time Orientation

This pack is intentionally declarative. It does not support every MCP server by shipping connector code. Instead, it provides a safe catalog and routing profile for servers that can be connected through existing `defaultspack` MCP mechanisms after explicit user approval.
