# SENTRY-SC continuation

Last updated: 2026-10-02

## Current state

The digital twin, discrete-time simulator, FastAPI contracts, adapters, and React console are already in place. There is no `TODO`/`FIXME` in source. `CONTINUATION.md` did not exist before this session.

Core walkthrough works: Overview twin, Compare of `SCN-BASELINE` / `SCN-ALPHA-OUTAGE` / `SCN-ALPHA-RECOVERY`, Stress test → Results with day playback.

## Completed this session

- **Playback graph edges** now use only `hotRouteIds` (`affectedEdges`). Previously `NetworkGraph` also highlighted any route touching a single impacted node, which painted a star around factories/customers instead of the cascade path.
- Added a vitest case: a route with only one impacted endpoint is not hot.

## Tests run

- `frontend`: `npm test` (vitest) — **6 passed**.
- Backend pytest was **not** re-run this session (no backend code changes).
- Browser: Compare of the three seeded scenarios succeeded; Results for `SCN-ALPHA-OUTAGE` loaded and the day slider moved to day 12; Overview still loads the baseline twin.

## Remaining (priority order)

1. **Stress-test recovery targets are hardcoded.** Expedite always uses `RTE-001`, capacity increase `RTE-002`, reallocate `WH-002`→`WH-003`. `restore_supplier` uses the disruption `target`, which is wrong for route/warehouse/demand events. Wire recovery fields to the selected node/route (and hide mismatched recoveries).
2. **Results `fitView` on every day change.** `NetworkGraph` always passes `fitView`, so playback can reset the camera each tick.
3. **Node details** still dumps raw JSON; render a readable entity panel.
4. **Engine coverage gaps:** no tests for `restore_supplier`, `restore_factory`, or `increase_route_capacity` (engine already implements them).
5. **SAP adapter** remains a stub (`available()` is `False`) — expected; do not claim a live connection.

## Next action

Implement Stress-test recovery targeting so route/node recoveries follow the user’s selected target instead of hardcoded demo IDs. Keep that change local to `frontend/src/pages/StressTest.tsx` plus a small helper test if you extract target-building logic.
