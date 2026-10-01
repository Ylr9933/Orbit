# Full-branch review: fixes and tidy-up of implemented code

`refactor/ts-rewrite` · base `4305fdc` (R4) · completed (no new features; pending user testing) · 2026-10-01T16:40:00+08:00

## Goal

Review the whole `refactor/ts-rewrite` branch (R0–R4) and fix correctness, security and robustness
problems in code that already exists. Unimplemented features stay out of scope; they are listed below.

## Changes

- **Daemon API / Web security** (`daemon/app.ts`, `lib/tokens.ts`, `records/index.ts`, `cluster/worker.ts`):
  constant-time token checks (shared with the worker API); cookie-authenticated writes must be
  same-origin (403 otherwise); `files/*` serves only regular files whose real path stays in the output
  directory, with `CSP: sandbox` + `nosniff` and RFC 5987 download names; malformed URL escapes → 400;
  `/login` `next` validated as a same-origin URL; numeric query parameters validated; `/wait` returns
  only after cleanup; a running process run's `log.txt` is streamed through the redactor.
- **Run service** (`runs/service.ts`, `runs/process.ts`, `executor/docker.ts`): the scheduler re-reads
  each queued run and deducts leased memory within a pass; cancel/timeout requested before a run's
  control entry exists is kept; `finalize` is idempotent; a GPU mismatch stops the container; docker
  inspect errors no longer look like "container gone" (recovery retries later); reattaching truncates
  the log to the recorded start offset instead of duplicating it; `docker wait` is retried; missing
  images are pulled into the run log first; containers without a GPU lease get
  `NVIDIA_VISIBLE_DEVICES=void`; `--mount` fields are CSV-quoted; log fds are closed; process-group
  liveness checks members' start times (pid reuse); `collect` paths cannot escape the container copy.
- **Cluster** (`cluster/service.ts`, `runs/service.ts`): a removed node's mirrors become `lost`;
  mirror sync ends only after the worker confirms cleanup; duplicate in-flight bundle submissions are
  merged; `node expose` restores the previous listener on failure; a failed bundle pack is `rejected`.
- **Bench / sessions**: Harbor `passEnv` (grader secrets) goes to the verify run, not the Agent's solve
  run; a job cancelled while a run was being submitted cancels that run; failure paths keep the solve's
  issues; compare keys stay unique for jobs with the same name, duplicate job ids are rejected;
  `effort` must be a plain word and is quoted in the Codex config; session ids are validated and Codex
  files matched exactly; vanished session files are tolerated.
- **Contracts**: mount targets absolute, distinct, without `..`, outside `/orbit` and `/workspace`;
  `collect` without `..`; stale R0 comments fixed.
- **Snapshot**: a diff git cannot produce is marked as incomplete instead of being silently truncated;
  the temporary index name is random.
- **CLI**: `--pass-env VAR`; `run --wait --json` prints one object; `sweep` rejects unused/invalid
  params; `--gpus` defaults to the number of `--gpu-ids`; `daemon --stop` uses the live daemon's pid;
  `daemon.json` written atomically; `ORBIT_AGENT` split on the first `:`; exec timeouts reported as 124.
- **Web** (`packages/web/src`, 22 files): non-overlapping polling, run-list events during loading kept,
  stream reconnect with health check, shared hotkey listener, encoded ids in links and safe decoding,
  "not found" only for 404, log cap (400k lines) and empty-regex fix, chart zoom kept across polls,
  error boundary per page, bounded metric fetches on Compare, smaller fixes (toasts, clamped percents).
- **Docs**: design §3 / §5 / §7 (auth, RunSpec fields, mount rules, `passEnv`, files route, pull,
  `NVIDIA_VISIBLE_DEVICES=void`, process cwd); README `orbit web`, `--image` in the dataset example;
  skill recommends `--pass-env` for secrets; `node expose` hint wording.

## Validation

| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| `pnpm verify` | 4305fdc + this change (workspace) | passed | biome, tsc, boundaries; orbit 80 passed / 3 skipped, web 6 passed; builds |
| `test/review.test.ts` (new) | same | passed | mount/collect validation, symlink escape in `outputFile`, path decoding, `expandGrid`, GPU memory tolerance, `runArgs` void env + CSV quoting |
| New cases in bench / sessions / daemon tests | same | passed | Harbor `passEnv` placement, duplicate compare names, session id traversal, cross-site cookie POST → 403 |
| Docker E2E (`ORBIT_E2E=1 ORBIT_E2E_GPUS=1`) | same | passed | 3/3 with real Docker and 1 GPU; no Orbit containers left |
| Image pull, daemon restart with log truncation, remote node removal on real machines | — | not_run | covered by code review and unit/daemon tests only |
| Web changes in a browser | — | not_run | typecheck, unit tests and build only |

## Next / open issues

- Not changed here (behaviour or design work rather than fixes): Harbor runs have no model-error
  invalidation (ASI only); a daemon crash between submitting a solve run and saving the trial can
  submit it again; bench groups may notify per run as well as per job; job page and compare page use
  different mean definitions; git submodules are skipped in snapshots without a warning.
- Hardening: bundle receive size limit and cache eviction; log redaction across chunk boundaries;
  backoff for cleanup retries; `ClusterService.stop()` does not await an in-flight dispatch; small
  duplicated helpers (tables, tag sanitising).
- User testing of R3/R4 as before.
