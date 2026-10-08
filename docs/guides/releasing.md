# Publishing Orbit

The first public npm release is pending. The package name is `@zjunlp/orbit`; the Claude Code
marketplace is `orbit` in `zjunlp/Orbit`, with plugin `orbit@orbit`.

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
use a registry mirror. Consumers need neither pnpm nor build scripts; the smoke check installs
with `--ignore-scripts` in a temporary directory, imports the public exports, invokes the CLI via
`npm exec --offline` (the npx execution path), starts a private daemon and requests its Web assets.
Docker/GPU prerequisites are probed for real; missing prerequisites on CI are reported without
pretending an experiment ran. The private daemon is stopped afterwards.

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

Update `packages/orbit/package.json` and, when plugin content changes, `plugin/.claude-plugin/plugin.json`.
Review, validate and merge the release. Publish a GitHub Release tagged `v<package version>`:
`.github/workflows/publish.yml` checks the version, verifies, packs, installs/tests that tarball and
publishes the same bytes. Stable releases use npm's `latest` tag; GitHub prereleases use `next`.
Do not trigger this workflow for a version already published locally.

Plugin updates ship through the GitHub marketplace; users run
`claude plugin marketplace update orbit && claude plugin update orbit@orbit`, then restart Claude Code.
This is a project marketplace, not a listing in Anthropic's official marketplace.

References: [pnpm publish overrides](https://pnpm.io/package_json#publishconfig),
[npm organization packages](https://docs.npmjs.com/creating-and-publishing-an-organization-scoped-package/),
[npm trusted publishing](https://docs.npmjs.com/trusted-publishers/),
[Claude Code marketplaces](https://code.claude.com/docs/en/plugin-marketplaces).
