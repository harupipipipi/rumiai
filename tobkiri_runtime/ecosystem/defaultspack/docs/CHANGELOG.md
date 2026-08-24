# Changelog

- Guarded defaultspack web UI local-storage reads and writes so restricted
  browser contexts and quota failures remain non-fatal.
- Restored clean packaged Launcher startup under Pack API v4 with a
  Launcher-owned, owner-only guardian token and authenticated panel readiness
  verification; no legacy Kernel API-token authority is reintroduced.
- Added defaultspack v2 compatibility layers.
- Added backend loaders, state manager, and setup pack selection helpers.
- Added thin UI module manifests for frontend discovery.
