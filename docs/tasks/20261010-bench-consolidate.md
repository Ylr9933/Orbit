# Consolidate completed benchmark retries
branch: fix/bench-consolidate · status: completed · updated: 2026-10-10

## Goal
Merge completed TB-Science retries into the original task matrix and remove failed runs through the daemon.

## Changes
- Preview-first consolidation API, client, CLI and Web action; keeps target trial IDs and source run IDs/artifacts.
- Refuses active or unclean runs, mismatched methods/options/metrics and replacement of valid results (including zero scores).
- Atomic ownership update in Store; obsolete artifacts deleted by existing RunService. Invalid task outcomes remain visible.
- Optional invalid-history/artifact pruning; no image or download-cache deletion.

## Validation
| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| Targeted fixture tests | working tree | passed | Real daemon/API/store/filesystem; explicit terminal-run fixtures, not experiments |
| pnpm verify | working tree | passed | 185 Orbit tests passed, 10 opt-in tests skipped; 5 script and 11 Web tests passed; formatting, types, boundaries and build passed |
| Actual TB-Science consolidation | working tree | passed | 8 valid retries adopted; original 65 identities preserved; 60 outcomes and 120 solve/verify outputs unchanged; 24 invalid runs and 11 source jobs removed |
| Live recovery and cleanup | working tree | passed | Active Agent retained container ID and start time; one root-owned staging remainder removed with an Orbit cleanup run; no leftovers |

## Next / open issues
- Integrate only the consolidation feature into main; the Harbor changes in the original branch ancestry are outside this merge.
- The existing daemon continues using its verified build; source integration does not restart experiments or replace the installed CLI.
- At initial application, one trial was pending in its own job; an Orbit collector adopts a valid result. Four unresolved environments retained their task outcomes without obsolete artifacts.
- Contract does not yet store immutable benchmark provenance; compatibility uses stored benchmark name, method, options and metrics. Caller must verify checkout identity.
