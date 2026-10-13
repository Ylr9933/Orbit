# Release dependency and license fixes
branch: fix/public-release-deps-licenses · status: completed · updated: 2026-10-13

## Goal
Remove the known source-map parsing vulnerability and distribute complete third-party license notices.

## Changes
- Update the transitive `source-map-js` dependency from 1.2.1 to 1.2.2 for CVE-2026-93749.
- Generate full notices for bundled Web dependencies, including font licenses, in every production build.
- Check license contents in the installed release tarball and document the MIT / presentation / third-party license scope.

## Validation
| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| Frozen install and full dependency audit | working tree | passed | Official npm registry; 229 dependencies, zero known vulnerability alerts |
| pnpm verify | working tree | passed | 194 Orbit, 11 Web and 5 script tests; 10 opt-in checks skipped; format, types, boundaries and builds passed |
| Pack and installed-package smoke | working tree | passed | CLI, exports, private daemon, Web assets and full license texts; doctor passed 8 real prerequisite checks |
| Docker/GPU/model execution | — | not_run | Build dependency, packaging and documentation changes only |

## Next / open issues
- No remaining issues for this change.
