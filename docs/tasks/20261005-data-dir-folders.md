# Data directory and folders
branch: feat/data-dir-folders · status: completed · updated: 2026-10-05

## Goal
1. Keep large run data off the home / system disk for every user, without relying on a symlink.
2. Organize runs and bench jobs into folders (e.g. all ResearchClawBench work) without moving files.

## Changes
- `OrbitPaths.data` (`ORBIT_DATA`, else `dataDir` in `<home>/config.json`, else home): runs, bench staging
  and code bundles; database, profiles and config stay in home. `orbit config [data <dir>]`.
- Doctor: `orbit data` and `docker data` checks with free space; `warn` on the system disk or below
  10% free (at least 50 GB, at most 500 GB). `DoctorCheck.warn`; Settings shows a Storage card. Resource probe measures the data disk.
- `Run.folder`, `BenchJob.folder` (`contracts.Folder`), `Run.sizeBytes` measured after cleanup (old runs
  measured in the background at start). Store: folder filter, `folders()`, `jobsIn()`.
- API `GET folders`, `POST folders/move` (a job and its runs move together), `POST folders/export`
  (copy runs, records, jobs and an index into an empty directory outside the data directory);
  `?folder=` on `POST runs`, `POST bench/jobs`, `GET runs`.
- CLI `--folder` on `run`, `sweep`, `bench run`; `ps -f`, `mv`, `folders`, `export`, `config`; folder and disk
  in `show`. Web: folder sidebar in Runs (`?folder=`), Move to folder dialog, folder / size chips.
- Docs: design §3/§5, READMEs, orbit skill, status.

## Validation
| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| `pnpm verify` | working tree | see commit | |
| Daemon test: separate data dir, folder move with a bench job, sizes, export | working tree | passed | external fake adapter, process backend |
| Real daemon on this machine (doctor, folders) | after build | see handoff | |

## Next / open issues
- Moving an existing data directory is manual (stop daemon, move `runs/ bench/ cache/`).
- No size-based cleanup or retention policy yet; folder delete goes through `orbit rm` per run / job.
