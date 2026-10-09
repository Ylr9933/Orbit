# Orbit presentation: product visuals and architecture
branch: docs/orbit-ppt-polish · status: completed · updated: 2026-10-09

## Goal
Refine the khaki editorial presentation with the supplied screenshots, a clear product narrative,
and accurate explanations of the architecture and module responsibilities.

## Changes
- Organize 15 slides: purpose (1–3), architecture (4–5), execution (6–8), review (9–10),
  extensions (11–13), first run (14), closing (15).
- Keep stable IDs for existing pages. Add `architecture` (dark, layout 10) and `modules` (light, layout 5).
- Use the supplied Web overview in `review` (dark, layout 10) and Feishu image in `phone`
  (hero light, layout 4), preserving screenshot content and original files.
- Use a dark terminal page for `first-run`; align typography, diagrams, page numbers and speaker notes.
- Ground claims in the current README, design/status, and completed Feishu/plugin task records.
- Update embedded Chinese font subsets, Feishu setup instructions, and the `zjunlp/Orbit` project link.

## Validation
| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| Presenter validator and inline JS parsing | final working tree | passed | 15 stable slide IDs / 15 matching notes; zero warnings; all four scripts parsed |
| Offline Chromium 153 rendering | final working tree | passed | All 15 pages at 1600×900 and 1280×720; no content overflow, external requests or script errors |
| Presenter and navigation | final working tree | passed | 15 interaction groups: keys/wheel/touch, pipeline, overview, notes, timers, rehearsal, auto advance, annotations, black/white/freeze, audience recovery and exit; 16:9 previews at two sizes |
| Screenshot and font integrity | final working tree | passed | Original image hashes unchanged; full screenshots use contain; embedded fonts cover every visible Chinese character; runtime scripts unchanged |
| PDF export | final working tree | passed | 15 landscape pages at 16:9, including screenshots |
| `pnpm verify` | 54851f7 + presentation changes | passed | 168 tests passed; 4 gated Docker tests skipped; types, lint, boundaries and builds passed. Biome skips the large embedded-font HTML; dedicated checks above cover it |
| `git diff --check` | final working tree | passed | No whitespace errors |
| Real Docker / GPU and physical projector | final working tree | not_run | Presentation-only changes; no execution code changed and no physical projector available |

## Next / open issues
- Open `docs/ppt/index.html`; retain `images/` beside it when sharing. Usage and the page plan are in `docs/ppt/README.md`.
- Development branch: `docs/orbit-ppt-polish`; user-authorized integration targets: local `main`, `origin/main`, and `xuehai/main`.
