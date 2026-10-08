# npm distribution and one-command Claude Code plugin installation
branch: feat/npm-plugin-install · status: completed · updated: 2026-10-08

## Goal
Use Orbit without cloning/building: an npm CLI with bundled Web UI and one-command Claude plugin installation.
User scope clarification: finish code and validation; do not publish yet.

## Changes
- Build public JS/type exports; pnpm packs compiled entrypoints, README, MIT license and Web assets.
- `orbit plugin install` delegates marketplace registration and user installation to Claude Code; handles local paths.
- Plugin 0.1.1 skills support npx; benchmark references work without a checkout.
- Isolated package smoke check in CI; GitHub Release / npm OIDC workflow; bilingual installation and release docs.
- Publish the tested tarball to npmjs.org explicitly, independent of the install registry mirror.

## Validation
| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| `pnpm verify` | final working tree | passed | Format/lint/types/boundaries, 150 tests, builds; 4 gated Docker tests skipped |
| `pnpm pack:release` + `pnpm smoke:package dist/zjunlp-orbit-0.1.0.tgz` | final working tree | passed | Install outside checkout with scripts disabled; bin, JS/types exports, npx path, private daemon, HTTP/Web/assets; doctor passed 8 real checks |
| Real Claude Code 2.1.289 | final working tree | passed | Manifests validated; local install and repeat install; npx from tarball installs plugin 0.1.1 with both skills, in temporary config |
| Skill validator (both skills) | final working tree | passed | Frontmatter validation |
| npm publish dry-run | final tarball | passed | Public access, npmjs.org; archive contains only package metadata, README, license and build artifacts |
| Workflow YAML / Git diff checks | final working tree | passed | YAML parsed, no whitespace errors; status within 40 lines |
| npm authentication probe | local environment | failed | `npm whoami`: ENEEDAUTH; account login needed for future publication |
| Registry publication / GitHub workflow execution | final working tree | not_run | User explicitly deferred publication; no push, release or workflow dispatch |
| Docker execution / GPU jobs | final working tree | not_run | Packaging and installer change; real doctor probes only, no experiment launched |

## Next / open issues
- When authorized: review/merge plugin changes, authenticate an authorized `@zjunlp` publisher, publish the tested tarball and verify public npx installation.
- Configure npm trusted publishing and GitHub environment `npm` before later automated releases.
- MCP remains unimplemented and is outside this installation change.
