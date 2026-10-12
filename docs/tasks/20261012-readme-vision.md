# README vision and navigation
branch: docs/readme-vision · status: completed · updated: 2026-10-12

## Goal
Present Orbit's cross-environment experiment and trajectory-learning vision, with clear entry points and an honest distinction between implemented behavior and future directions.

## Changes
- Align English, Chinese and package README titles and introductions; reflect the vision in design §1.
- Add local SVG badges, navigation, capability tables, a source-install quickstart, roadmap and documentation links; retain detailed commands in disclosure blocks.
- Keep embodied device backends and automated trajectory learning explicitly aspirational. Personal experiment records remain outside source documentation.

## Validation
| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| pnpm verify, initial attempt | documentation working tree | failed | Existing snapshot test missed a tracked modification; isolated rerun passed all 3 tests |
| pnpm verify, full rerun | documentation working tree | passed | 192 Orbit, 11 Web and 5 script tests; 10 opt-in tests skipped; format, types, boundaries and builds passed |
| Links and GitHub Markdown rendering | documentation working tree | passed | Local paths and fragments resolve; tables, code and disclosure blocks render in both languages |
| Browser review | documentation working tree | passed | GitHub-rendered HTML checked at desktop and narrow mobile widths with local badge assets |
| Docker/GPU/model execution | — | not_run | Documentation and SVG assets only; runtime behavior unchanged |

## Next / open issues
- Revisit the source-install emphasis after the first public npm release; update roadmap claims only when implementation and validation support them.
