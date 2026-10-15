# Structure and Web UX
branch: refactor/opt5-structure · status: completed · updated: 2026-10-15

## Goal
Split large modules without changing execution behavior; improve merge review, complete run lists,
background polling and private state permission checks (batch 5, items 31–41).

## Changes
- Extract pure bench consolidation planning, summary/comparison and usage rows; split trial steps and share Agent-method checks. Cleanup aggregation already used classify and remains shared.
- Split RunService execution helpers, contract domains, HTTP route groups and CLI run helpers behind stable entry points. Share private JSON publication.
- Add a labelled native merge dialog with preview, typed confirmation and digest validation; split Runs/Bench components.
- Add run cursors through store/API/client/Web; retain SSE updates/deletions during pagination and reload after a concurrent reconnect. Pause hidden-tab polling, including logs.
- Check/tighten owned home symlink targets and existing private JSON/log/lock files; refuse links below state roots and foreign ownership.

## Validation
| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| Final pnpm verify | working tree on 0c8de95 | passed | Format/lint, types, boundaries, 5 script + 364 Orbit + 26 Web tests, Web/CLI/declaration builds. 10 opt-in Docker tests skipped; no existing expectations changed. |
| Initial verify | working tree on 0c8de95 | failed | Fixed a non-clonable planner fixture. Process fixture cleanup needed an explicit empty container inventory instead of the command-blocking guard. |
| Second verify | working tree on 0c8de95 | failed | Tests passed; declaration build required an explicit Response return type on the extracted error handler. Fixed and final verify passed. |
| Snapshot retry | working tree on 0c8de95 | passed | Third verify hit the known changedFiles flake; all 7 snapshot tests passed alone and in final verify. No snapshot code or expectations changed. |
| Markdown-only Biome invocation | working tree on 0c8de95 | failed | Biome ignores Markdown and reported no processed files; git diff --check passes and status.md is 39 lines. |
| Real Docker/GPU/auth execution | working tree on 0c8de95 | not_run | Prohibited for this batch. Tests use temporary homes, fake adapters and an explicit empty Docker inventory; other Docker/GPU commands are blocked. |
| Browser keyboard/visual check | working tree on 0c8de95 | not_run | Pure request/polling tests and server-rendered dialog assertions pass; native dialog focus, Esc and layout need browser review. |

## Next / open issues
Runner owns staging/commit; message is prepared outside the checkout. Browser keyboard/layout review and real executor checks remain manual.
