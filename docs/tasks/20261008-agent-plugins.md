# Codex, dsh and pi plugin distribution
branch: feat/npm-plugin-install · status: completed · updated: 2026-10-08

## Goal
Install the same Orbit skills in Claude Code, Codex, DeepSeek Harness and pi with one command.
User authorized merging into main and pushing both remotes; npm publication remains deferred.

## Changes
- Native installers behind `orbit plugin install [claude|codex|dsh|pi]`; Claude remains the default.
- Codex portable manifest/marketplace, npm pi metadata, bundled canonical skills and a thin dsh provider adapter.
- Explicit dsh profile; reject reserved/skill-less built-in profiles. Copy local packages with `file:` so host dependencies resolve.
- Match dsh/pi npm versions to the invoking CLI; keep registrations independent of the npx cache.
- Installer regressions, package payload checks, bilingual docs and release guidance.
- CI follow-up: hold the fake benchmark's real process until usage is sampled, replacing the timing assumption behind its intermittent assertion failure. No production behavior changed.

## Validation
| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| `pnpm verify` | final working tree | passed | 168 tests; 4 gated Docker tests skipped; format/lint/types/boundaries/builds |
| `pnpm install --frozen-lockfile --ignore-scripts` | final lockfile | passed | Optional host peer resolves for workspace development |
| `pnpm pack:release` + `pnpm smoke:package dist/zjunlp-orbit-0.1.0.tgz` | final tarball | passed | External install, bin/npx/exports, daemon/Web; 8 real doctor checks; skill bytes, pi metadata, dsh entry; no dsh runtime installed |
| Claude Code 2.1.289 | final tarball CLI + local marketplace | passed | Temporary config; install/repeat, enabled plugin 0.1.2, native `plugin details` lists both skills and computes their body token counts |
| Codex 0.161.0 | final tarball CLI + local marketplace | passed | Temporary home; install/repeat; app-server `skills/list` and `fs/readFile`, exact canonical bodies |
| dsh 0.1.6-alpha.1 + pnpm 10.32.1 | final tarball | passed | Temporary headless profile; install/repeat, one bundle; native Loader with real skills service/provider `list`/`get`, both bodies; no model call |
| pi 1.1.0 (`@earendil-works/pi-coding-agent`) | final extracted tarball | passed | Temporary user settings; install/repeat; real DefaultResourceLoader and read tool load both skills |
| Real installer failure paths | final tarball CLI | passed | Missing agent binary, missing dsh profile and missing local source fail without installation |
| Initial dsh environment probe | local Corepack default | failed | Corepack selected pnpm 12.4.1 but looked for absent `pnpm.cjs`; isolated tests used the existing real pnpm 10.32.1 executable, without changing user config |
| npm publish dry-run / archive contents | final tarball | passed | Public npmjs.org target, 45 expected files; no source tree or runtime artifacts |
| Public npm install / registry publication | final code | not_run | Publication explicitly deferred; registry defaults covered by command fakes, real agent checks used local candidate artifacts |
| Model inference / GPU experiments | final code | not_run | Plugin loading needs no inference; Docker/GPU prerequisites probed by doctor only |
| Initial remote CI | `0db58ad` | failed | origin hit the existing benchmark usage timing race; xuehai passed verify and package smoke. Follow-up synchronizes the fixture with actual sampling. |
| Usage timing regression + `pnpm verify` | `fix/bench-usage-test-sync` | passed | Real process sampling with the explicit fake benchmark; full suite still 168 passed / 4 gated Docker tests skipped |

## Next / open issues
- Publish and check registry-based npx installation when authorized and npm authentication is ready.
- dsh requires a working pnpm and a profile containing the skills service; pi local directories must remain on disk.
- MCP, in-container dsh/pi harnesses and session parsing remain outside this change.
