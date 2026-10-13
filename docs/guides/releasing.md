# Publishing Orbit

The first public npm release is pending. The package name is `@zjunlp/orbit`; the Claude Code / Codex
marketplace is `orbit` in `zjunlp/Orbit`, with plugin `orbit@orbit`. dsh and pi use the same npm package.

## Validate the artifact

Use Node.js from `.node-version` and the pnpm version from the root `package.json`.

```bash
pnpm install --frozen-lockfile
pnpm verify
pnpm pack:release
pnpm smoke:package dist/zjunlp-orbit-0.1.0.tgz
```

`pack:release` builds current sources, including the Web UI, and writes the tarball to `dist/`.
Use **pnpm pack**, not `npm pack` on the source directory: pnpm applies `publishConfig.exports`,
replacing workspace TypeScript entrypoints with compiled JavaScript and declarations. Publish the
tested tarball with npm. `publishConfig.registry` pins publication to npmjs.org even when installs
use a registry mirror. CLI consumers need neither pnpm nor build scripts; the smoke check installs
with `--ignore-scripts` in a temporary directory, imports the public exports, invokes the CLI via
`npm exec --offline` (the npx execution path), starts a private daemon and requests its Web assets.
Docker/GPU prerequisites are probed for real; missing prerequisites on CI are reported without
pretending an experiment ran. The private daemon is stopped afterwards.

The tarball must include `LICENSE` for Orbit and `dist/web/THIRD_PARTY_LICENSES.md`
for bundled Web dependencies. Vite generates the latter from the installed dependency
licenses on every production build; the smoke check verifies full license texts,
including Inter and JetBrains Mono's OFL notices. Keep the repository's
[license scope](../../THIRD_PARTY_NOTICES.md) accurate when adding third-party material.

For Claude Code, validate and install the candidate in a temporary config directory:

```bash
orbit_plugin_test=$(mktemp -d)
CLAUDE_CONFIG_DIR="$orbit_plugin_test" claude plugin validate .
CLAUDE_CONFIG_DIR="$orbit_plugin_test" claude plugin validate plugin
CLAUDE_CONFIG_DIR="$orbit_plugin_test" pnpm orbit plugin install --source .
CLAUDE_CONFIG_DIR="$orbit_plugin_test" claude plugin list --json
```

This calls the real Claude CLI without changing your normal plugin settings. Both `orbit` and
`orbit-bench` must appear in the installed plugin. Repeat the install to check an existing
registration. It does not invoke a model or spend inference credits.

For the other native installers, use isolated agent homes as well (the CLIs must be on PATH;
dsh also requires a working pnpm):

```bash
orbit_plugin_test=$(mktemp -d)
mkdir -p "$orbit_plugin_test/codex"
CODEX_HOME="$orbit_plugin_test/codex" pnpm orbit plugin install codex --source .
CODEX_HOME="$orbit_plugin_test/codex" codex plugin list --json
DSH_HOME="$orbit_plugin_test/dsh" pnpm orbit plugin install dsh --profile headless --source ./dist/zjunlp-orbit-0.1.0.tgz
DSH_HOME="$orbit_plugin_test/dsh" dsh --profile headless --dump-config
tar -xzf dist/zjunlp-orbit-0.1.0.tgz -C "$orbit_plugin_test"
PI_CODING_AGENT_DIR="$orbit_plugin_test/pi" pnpm orbit plugin install pi --source "$orbit_plugin_test/package"
PI_CODING_AGENT_DIR="$orbit_plugin_test/pi" pi list
```

Repeat each install and confirm a single enabled plugin/bundle/package. Verify skills through
the host, not just files: Claude `plugin details orbit@orbit`, Codex app-server `skills/list` and
`fs/readFile`, dsh's native Loader + SkillRegistry `list`/`get`, and pi's `DefaultResourceLoader`
and read tool. Both bodies must match the canonical `plugin/skills/` files. These checks need
no model call; keep them separate from the explicit command fakes in unit tests. The package
smoke also checks skill bytes, pi metadata and the dsh entry without installing the dsh runtime.
For the tested versions and profile requirements, see [the plugin guide](../../plugin/README.md).

## First npm publication

An npm account needs permission to publish public packages under the `@zjunlp` organization.
Authenticate in your terminal; never put a token or OTP in Git, an issue or a task record.

```bash
npm login
npm whoami
npm publish ./dist/zjunlp-orbit-0.1.0.tgz --access public
```

The tested code and plugin should be reviewed and merged to `zjunlp/Orbit` before publication,
because `orbit plugin install` fetches that repository. Remove the first-release-pending notices
once publication succeeds. Verify from a directory outside the checkout:

```bash
npx -y @zjunlp/orbit@0.1.0 doctor
npx -y @zjunlp/orbit@0.1.0 plugin install
```

## Later releases

Configure an npm trusted publisher in the package's npm settings: GitHub owner `zjunlp`, repository
`Orbit`, workflow `publish.yml`, environment `npm`. Create that GitHub environment with the desired
release approvals. The workflow uses OIDC and provenance, with no long-lived npm token.

Update `packages/orbit/package.json` and, when plugin content changes, both `plugin/plugin.json` and
`plugin/.claude-plugin/plugin.json` (keep their plugin versions equal).
Review, validate and merge the release. Publish a GitHub Release tagged `v<package version>`:
`.github/workflows/publish.yml` checks the version, verifies, packs, installs/tests that tarball and
publishes the same bytes. Stable releases use npm's `latest` tag; GitHub prereleases use `next`.
Do not trigger this workflow for a version already published locally.

Plugin updates ship through the GitHub marketplace; users run
`claude plugin marketplace update orbit && claude plugin update orbit@orbit`, then restart Claude Code.
Codex, dsh and pi management commands are in [the plugin guide](../../plugin/README.md).
These are project marketplaces, not listings in an official curated marketplace.

References: [pnpm publish overrides](https://pnpm.io/package_json#publishconfig),
[npm organization packages](https://docs.npmjs.com/creating-and-publishing-an-organization-scoped-package/),
[npm trusted publishing](https://docs.npmjs.com/trusted-publishers/),
[Claude Code marketplaces](https://code.claude.com/docs/en/plugin-marketplaces).
