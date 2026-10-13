# Third-party notices

Orbit's original source code is licensed under the MIT License in `LICENSE`.
Third-party code, fonts and presentation materials retain their respective licenses.

## Bundled Web UI

The Web UI bundles Inter and JetBrains Mono under the SIL Open Font License 1.1,
and React, React DOM, Scheduler, TanStack Virtual, Anser and uPlot under the MIT License.

Each production build generates `packages/web/dist/THIRD_PARTY_LICENSES.md` from
the dependencies actually bundled by Vite. It contains package names, versions,
copyright notices and full license texts, including the fonts' OFL terms.
The npm package includes this file at `dist/web/THIRD_PARTY_LICENSES.md`.
`pnpm smoke:package` checks the installed tarball for these notices.

CLI runtime dependencies are installed separately by npm and retain the license
files distributed in their own packages.

## Presentation

The presentation in `docs/ppt/` derives from guizang-ppt-skill and is licensed
under AGPL-3.0. Its Motion module uses the MIT License; its Noto CJK and Liberation
fonts use the SIL Open Font License. Attribution, source revision and complete
license texts are retained in the
[presentation documentation](https://github.com/zjunlp/Orbit/blob/main/docs/ppt/README.md#来源与许可)
and its `licenses/` directory. These presentation files are not included in the
Orbit npm package.
