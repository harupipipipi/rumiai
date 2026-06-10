<!-- docs-i18n-links:start -->
[EN](../../defaultspack_v2.md) | [JP](../ja/defaultspack_v2.md) | [KR](./defaultspack_v2.md) | [CN](../zh-cn/defaultspack_v2.md)
<!-- docs-i18n-links:end -->

# defaultspack v2

> **Legacy 메모**: 개요 전용 이전 메모입니다. 현재 설명은 [defaultspack-v2.md](./defaultspack-v2.md)을 참조하십시오.

`defaultspack` is now a tracked first-class pack under `ecosystem/defaultspack/`.

## What changed

- Canonical backend API paths now live under `/api/defaultspack/*`.
- Setup-pack discovery comes from `ecosystem/setup_pack/*/pack.json`.
- Module state is cataloged and persisted by defaultspack backend module helpers.
- Defaultspack operations are executed through `functions/` instead of direct block imports.
- Pack modification requests now enforce slot/fullscreen conflict rules before approval.
- Legacy CLI/HTTP fallback transports dispatch through `bridge/block_adapter.py` instead of importing block handlers directly.

## Module model

Each module exposes:

- §루미§0§
- §루미§0§
- §루미§0§
- §루미§0§
- §루미§0§

Dependency failures degrade dependents without taking down the whole pack.

## Main endpoints

- §루미§0§
- §루미§0§
- §루미§0§
- §루미§0§
- §루미§0§
- §루미§0§
- §루미§0§
- §루미§0§
- §루미§0§
- §루미§0§
- §루미§0§
- §루미§0§
- §루미§0§
- §루미§0§
- §루미§0§
- §루미§0§
- §루미§0§

## Setup flow

The setup UI under `/setup` asks whether each discovered setup pack should be included at startup.
Selected setup packs are installed together and receive `all OK` grants from setup.

`supports_all_ok` is repository-managed trusted setup-pack metadata under
`ecosystem/setup_pack/*`. Upstream treats only maintainer-reviewed setup pack
definitions as trusted. Forks may add their own setup packs, but doing so is the
same as modifying trusted source in that fork; it is not a separate runtime
vulnerability boundary.

## Pack modification flow

Pack changes can be staged first, then submitted as either:

- §루미§0§
- §루미§0§

Both produce an approval-backed request record before any apply occurs.

Conflict policy:

- fullscreen requests are exclusive across active pending/applied requests
- exclusive requests cannot share the same slot
- non-exclusive same-slot frontend requests are preserved, but flagged for explicit active selection
