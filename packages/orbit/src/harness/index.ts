import {
  chmodSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  realpathSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { delimiter, dirname, join } from "node:path";
import { type AuthEntry, parseCodexLogin, secretValues } from "../auth/index.ts";
import type { Harness } from "../contracts/index.ts";
import { exec } from "../lib/exec.ts";

/** Where the Agent home lives inside the container (under the `/orbit` mount). */
export const AGENT_HOME = "/orbit/agent";
const CODEX_MOUNT = "/opt/orbit/codex";
const CLAUDE_MOUNT = "/opt/orbit/claude";

export interface HostCli {
  harness: Harness;
  /** Host path mounted read-only into the container. */
  source: string;
  /** The executable on the host (for `--version`). */
  hostBin: string;
  target: string;
  /** Directories inside the container to put on PATH. */
  pathDirs: string[];
  version: string;
}

export class HarnessError extends Error {}

function which(cmd: string, env: NodeJS.ProcessEnv): string | null {
  for (const d of (env.PATH ?? "").split(delimiter)) {
    if (!d) continue;
    const p = join(d, cmd);
    try {
      if (statSync(p).isFile()) return realpathSync(p);
    } catch {}
  }
  return null;
}

/** Find a directory containing `codex-package.json` (the npm vendor layout) below `root`. */
function findCodexVendor(root: string, depth = 6): string | null {
  if (existsSync(join(root, "codex-package.json"))) return root;
  if (depth === 0) return null;
  let names: string[] = [];
  try {
    names = readdirSync(root);
  } catch {
    return null;
  }
  for (const n of names) {
    const p = join(root, n);
    try {
      if (!statSync(p).isDirectory()) continue;
    } catch {
      continue;
    }
    const hit = findCodexVendor(p, depth - 1);
    if (hit) return hit;
  }
  return null;
}

/**
 * Locate the Codex CLI on the host. Codex ships a static musl binary, so it runs in any Linux image.
 * `ORBIT_CODEX_DIR` may point at the vendor directory (with `codex-package.json`) or a `codex` binary.
 */
export function locateCodex(env: NodeJS.ProcessEnv = process.env): Omit<HostCli, "version"> | null {
  const override = env.ORBIT_CODEX_DIR;
  const start = override ?? which("codex", env);
  if (!start || !existsSync(start)) return null;
  if (statSync(start).isFile() && !start.endsWith(".js")) {
    return {
      harness: "codex",
      source: start,
      hostBin: start,
      target: `${CODEX_MOUNT}/bin/codex`,
      pathDirs: [`${CODEX_MOUNT}/bin`],
    };
  }
  // npm install: <pkg>/bin/codex.js with the binary in <pkg>/node_modules/@openai/codex-<platform>/vendor/<triple>.
  const pkg = statSync(start).isDirectory() ? start : dirname(dirname(start));
  const vendor = findCodexVendor(pkg);
  if (!vendor) return null;
  const meta = JSON.parse(readFileSync(join(vendor, "codex-package.json"), "utf8")) as {
    entrypoint?: string;
    pathDir?: string;
  };
  const entry = meta.entrypoint ?? "bin/codex";
  return {
    harness: "codex",
    source: vendor,
    hostBin: join(vendor, entry),
    target: CODEX_MOUNT,
    pathDirs: [
      join(CODEX_MOUNT, dirname(entry)),
      ...(meta.pathDir ? [join(CODEX_MOUNT, meta.pathDir)] : []),
    ],
  };
}

/** Locate the native Claude Code binary (needs glibc in the image). `ORBIT_CLAUDE_BIN` overrides. */
export function locateClaude(
  env: NodeJS.ProcessEnv = process.env,
): Omit<HostCli, "version"> | null {
  const bin = env.ORBIT_CLAUDE_BIN ?? which("claude", env);
  if (!bin || !existsSync(bin) || bin.endsWith(".js") || bin.endsWith(".cjs")) return null;
  return {
    harness: "claude-code",
    source: bin,
    hostBin: bin,
    target: `${CLAUDE_MOUNT}/claude`,
    pathDirs: [CLAUDE_MOUNT],
  };
}

const cache = new Map<Harness, Promise<HostCli | null>>();

/** The host CLI for a harness with its version; cached for the daemon's lifetime. */
export function hostCli(harness: Harness): Promise<HostCli | null> {
  let p = cache.get(harness);
  if (!p) {
    p = (async () => {
      const loc = harness === "codex" ? locateCodex() : locateClaude();
      if (!loc) return null;
      const r = await exec(loc.hostBin, ["--version"]);
      return { ...loc, version: r.code === 0 ? r.stdout.trim() : "unknown" };
    })();
    cache.set(harness, p);
    // Retry next time if the CLI was missing (it may be installed later).
    void p.then((v) => v ?? cache.delete(harness));
  }
  return p;
}

export interface Prepared {
  mounts: { source: string; target: string; mode: "ro" }[];
  /** Non-secret environment. */
  env: Record<string, string>;
  /** Secret environment, passed through a private `--env-file`. */
  secretEnv: Record<string, string>;
  /** Strings to redact from logs. */
  secrets: string[];
  cli: HostCli;
}

const tomlString = (s: string) => JSON.stringify(s);

/** Codex config: the container is the sandbox, so Codex itself runs without approvals or sandboxing. */
export function codexConfig(entry: AuthEntry): string {
  const p = entry.profile;
  const lines = ['approval_policy = "never"', 'sandbox_mode = "danger-full-access"'];
  if (p.model) lines.push(`model = ${tomlString(p.model)}`);
  if (p.kind === "relay") {
    lines.push(
      'model_provider = "orbit"',
      "",
      "[model_providers.orbit]",
      'name = "Orbit relay"',
      `base_url = ${tomlString(p.baseUrl ?? "")}`,
      'env_key = "ORBIT_RELAY_API_KEY"',
      'wire_api = "responses"',
    );
  }
  return `${lines.join("\n")}\n`;
}

/**
 * Write the Agent home under `agentDir` (mounted at /orbit/agent) and return the mounts and environment
 * that make the host CLI usable with this profile inside the container.
 */
export async function prepareHarness(entry: AuthEntry, agentDir: string): Promise<Prepared> {
  const p = entry.profile;
  const cli = await hostCli(p.harness);
  if (!cli) {
    throw new HarnessError(
      p.harness === "codex"
        ? "codex CLI not found on the daemon's PATH (set ORBIT_CODEX_DIR)"
        : "native claude binary not found on the daemon's PATH (set ORBIT_CLAUDE_BIN)",
    );
  }
  const env: Record<string, string> = { ...p.env, DISABLE_AUTOUPDATER: "1" };
  const secretEnv: Record<string, string> = {};

  if (p.harness === "codex") {
    const home = join(agentDir, "codex");
    mkdirSync(home, { recursive: true });
    env.CODEX_HOME = `${AGENT_HOME}/codex`;
    writeFileSync(join(home, "config.toml"), codexConfig(entry));
    if (p.kind === "login") writePrivate(join(home, "auth.json"), entry.secret);
    else if (p.kind === "api-key")
      writePrivate(join(home, "auth.json"), JSON.stringify({ OPENAI_API_KEY: entry.secret }));
    else secretEnv.ORBIT_RELAY_API_KEY = entry.secret;
  } else {
    const home = join(agentDir, "claude");
    mkdirSync(home, { recursive: true });
    env.CLAUDE_CONFIG_DIR = `${AGENT_HOME}/claude`;
    if (p.model) env.ANTHROPIC_MODEL = p.model;
    if (p.kind === "login") secretEnv.CLAUDE_CODE_OAUTH_TOKEN = entry.secret;
    else if (p.kind === "api-key") secretEnv.ANTHROPIC_API_KEY = entry.secret;
    else {
      env.ANTHROPIC_BASE_URL = p.baseUrl ?? "";
      secretEnv.ANTHROPIC_AUTH_TOKEN = entry.secret;
    }
  }
  return {
    mounts: [{ source: cli.source, target: cli.target, mode: "ro" }],
    env,
    secretEnv,
    secrets: secretValues(entry),
    cli,
  };
}

function writePrivate(file: string, text: string): void {
  writeFileSync(file, text, { mode: 0o600 });
  chmodSync(file, 0o600);
}

/** Credential files an Agent may leave in its home; removed after the run. */
const CREDENTIAL_FILES = ["codex/auth.json", "claude/.credentials.json"];

/**
 * After a run: return a refreshed Codex login (newer `last_refresh`) to write back, and delete
 * credential files from the Agent home. The rest of the home (sessions, logs) stays with the run.
 */
export function finishHarness(entry: AuthEntry | null, agentDir: string): { refreshed?: string } {
  const out: { refreshed?: string } = {};
  if (entry?.profile.harness === "codex" && entry.profile.kind === "login") {
    const file = join(agentDir, "codex", "auth.json");
    try {
      const text = readFileSync(file, "utf8");
      const now = parseCodexLogin(text);
      const before = parseCodexLogin(entry.secret);
      if ((now.last_refresh ?? "") > (before.last_refresh ?? "")) out.refreshed = text;
    } catch {}
  }
  for (const f of CREDENTIAL_FILES) rmSync(join(agentDir, f), { force: true });
  return out;
}

/** `PATH` for the container: harness directories first, then the image's own PATH. */
export function containerPath(pathDirs: string[], imagePath: string | null): string {
  const base = imagePath || "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin";
  return [...pathDirs, base].join(":");
}
