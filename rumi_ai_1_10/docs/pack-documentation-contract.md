<!-- docs-i18n-links:start -->
[EN](./pack-documentation-contract.md) | [JP](./i18n/ja/pack-documentation-contract.md) | [KR](./i18n/ko/pack-documentation-contract.md) | [CN](./i18n/zh-cn/pack-documentation-contract.md)
<!-- docs-i18n-links:end -->

# Pack Documentation Contract

Common rules for consolidating Pack-specific docs into `ecosystem/<pack_id>/docs/`.

## Responsibility Split

`rumi_ai_1_10/docs/` only contains runtime common docs and pack common rules.

- Runtime common explanations such as kernel, flow, approval, grant, etc.
- How to make a pack
-docs terms

`ecosystem/<pack_id>/docs/` only puts the description specific to that Pack.

- Pack Responsibilities
- Mounting structure
- flows / functions / handlers / routes
- How to operate
- Constraints

The root docs do not describe the Pack itself. It only has the entry link to the Pack and the common terms.

## Required Files

Each Pack has at least:

- `ecosystem/<pack_id>/README.md`
- `ecosystem/<pack_id>/docs/README.md`
- `ecosystem/<pack_id>/docs/architecture.md`
- `ecosystem/<pack_id>/docs/interfaces.md`
- `ecosystem/<pack_id>/docs/operations.md`

Responsibilities of each file:

- `README.md`: 3 minute overview, what we offer, what we don't offer, entry to docs
- `docs/README.md`: Table of contents of docs in pack, reading guide, guide for first-time readers
- `docs/architecture.md`: Responsibilities, main directories, execution paths, and contact points with runtime
- `docs/interfaces.md`: flows / functions / handlers / routes / events / stores / required secrets / network / grants
- `docs/operations.md`: Startup method, development method, testing method, common breakage methods, confirmation points when making changes

## Conditionally Required Files

Packs with that functionality put additional docs.

- `docs/flows.md`: When having flow / modifier

## Cross-Link Rules

- When describing a Pack from the root docs, keep it to a short introduction and entry link.
- Pack-specific instructions link to `ecosystem/<pack_id>/docs/README.md`
- Individual docs within a pack can be traced from `docs/README.md` if necessary.

## PR Rule

The following changes will require a docs update.

- Added new flow/modifiers
- Added new functions / handlers / routes
- required secrets / grants / network changed
- The startup method and operation method have changed
- Pack's responsibilities have changed.

## Scaffold Expectation

`pack_scaffold` maintains the required docs for the contract. When creating a new Pack, the goal is for the README and `docs/README.md` / `architecture.md` / `interfaces.md` / `operations.md` to naturally align.
