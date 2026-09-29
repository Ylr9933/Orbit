---
record_version: 1
task_id: "20260929-web-token-route-71ac9e"
title: "Consume login links during same-tab hash navigation"
branch: "fix/web-login-route-20260929"
base_commit: "2cb4b02786ca6e32c92d038a8e9881575e227c62"
work_status: in_progress
updated_at: "2026-09-29T11:10:00.133959+08:00"
pull_request: null
---

## Goal and acceptance

- Fix the reported page-not-found when opening a token login link in an already loaded tab.
- Consume the new token, remove it from the URL and navigate to experiments, including after logout and service-token rotation; preserve ordinary deep links and unknown-route handling.
- Verify browser reproduction before the change, regression checks, frontend type/build checks and local asset delivery. Preserve user image.png and runtime data.

## Changes

- The App now consumes token links on hashchange as well as initial mount, updating sessionStorage and React token state before resolving the experiment route. URL cleanup preserves the query string.
- Added browser regressions for same-document login, rotated-token request headers, login after logout and genuine unknown routes; existing benchmark workflow checks still pass. Updated the Web usage guide.

## Decisions

- Reuse the existing session-token reader for initial load and subsequent hash changes. No backend/session protocol changes and no service restart required.
- Follow-up to the delivered Web changes; keep the project overview unchanged for this focused fix.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Live browser reproduction | 2cb4b02 | passed | Fresh login shows experiments; setting the same token hash in the loaded tab shows page-not-found. Used private token without logging it. |
| `pnpm check`; `pnpm build` | Task source on 2cb4b02; JS index-COy5JaaC.js | passed | Biome, TypeScript and production build. |
| `node tests/web/benchmark.smoke.cjs` | Same Web source | passed | Same-document login, rotated token via explicit HTTP fixture, logout/reconnect, actual unknown route; existing batch/review/evidence/desktop/mobile workflows. |
| `uv run --locked python scripts/ci/check_repository.py`; `git diff --check` | Task documentation/source | passed | Policy mirrors, local links, whitespace; user image.png untouched. |
| Backend/model/Docker/GPU tests | None | not_run | Frontend-only navigation change; no runtime protocol, execution or data change. |

## Open items and blockers

- Implementation and regression checks passed; local asset delivery remains.

## Next steps

- Fix hash navigation, add browser regression coverage and rebuild the locally served frontend.

## Compatibility and rollback

- Frontend only. Existing fragment-token login/sessionStorage contract stays unchanged; revert on a task branch and rebuild assets to roll back. No runtime data migration.
