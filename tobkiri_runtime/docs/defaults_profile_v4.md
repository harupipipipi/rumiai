# Canonical Defaults Profile v4

The bundled `defaults` Profile is the sole canonical product Profile currently
defined by the finite Defaultspack v4 bundle. `shell.tauri.default` and
`shell.cli.default` are distinct Shell providers admitted by the bundle. They
are not Profile personas: a named Profile exists only when its entire Base,
Shell, Application, Pack set, requested edges, and presentation artifacts have
one generated authoritative definition. The current CLI Shell therefore does
not create a second selector row by itself.

## Authoritative composition

Resolution starts only from `ecosystem/defaultspack/v4/bundle.lock.json`. The
locked Profile source selects:

- `defaults-basepack` as the Base definition;
- `shell.tauri.default` as the exact `app.shell.v1` provider;
- `runtime.tauri.application.default` as the Application Pack;
- the explicit Defaults provider Pack set and its deterministic dependency
  closure;
- caller-specific requested Contract/Operation edges and opaque Authority
  references.

The resulting ProfileLock and ResolvedPlan both bind the source definition
digest, selected catalog revision, bundle-lock byte digest, Base and Shell
definition digests, Application manifest digest, requested-edge digest,
constraint digest, closure digest, provenance digest, Authority snapshot, and
SecurityEpoch. Each Plan binding includes the exact caller Function ID, target
FunctionPrincipal, Contract/Operation, opaque Authority reference, requested
scope digest, execution domain kind, and adapter chain.

Activation adds the exact Profile revision, ProfileLock digest, ResolvedPlan
digest, catalog and bundle digests, closure digest, Authority snapshot,
SecurityEpoch, and monotonically increasing fencing token. Restart reloads the
atomic activation envelope and rejects any stale or independently re-digested
Profile, Lock, Plan, activation, Authority reservation, epoch, or fence.

## Transactions and settings

Named Profile selection is the four-step server ceremony:

```text
resolve -> review -> Authority approval -> activation
```

The candidate is session-, predecessor-, catalog-, definition-, bundle-, and
digest-bound, expires server-side, and is consumed once. Named selection must
match the canonical Profile Pack set exactly. Optional Pack installation,
approval, enablement, and disablement remain the separate Defaults Pack-set
transaction; those operations derive a new immutable Profile closure on the
server and never trust client `approved` or `enabled` fields.

User Settings are a separate Launcher-local projection. Profile activation can
change only runtime Profile settings and cannot mutate User Settings.

## Generation and verification

The canonical bundle is generated only by:

```bash
python scripts/generate_defaultspack_v4_bundle.py
python scripts/generate_defaultspack_v4_bundle.py --check
```

Generation must be deterministic across consecutive runs. The complete-v4,
architecture, integrity, boundary, and checked-in evidence generators remain
the release authority; runtime Registry or installed-Pack discovery is never a
Profile source.
