"""Adapters (owner A): all external I/O lives here.

Each adapter turns one live source into Scenario inputs or Disruption-shaped
flags. Adapters return (result, fetched_at), never raise to callers, and fall
back to the last snapshot with stale_since set on failure. The simulator
(src/sim, src/twin) must never import from this package.
"""
