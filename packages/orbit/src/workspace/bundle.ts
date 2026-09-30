// Content-addressed code bundles moved from the primary to worker nodes. A bundle is a directory
// (a code snapshot, a Dockerfile context or a method bundle) identified by the hash of its tree; a
// worker keeps each received bundle once under `cache/bundles/<hash>` and reuses it for later runs.
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { createReadStream, existsSync } from "node:fs";
import { lstat, mkdir, mkdtemp, readdir, readlink, rename, rm } from "node:fs/promises";
import { join } from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";

export const MAX_BUNDLE_BYTES = 2 * 1024 ** 3;
export const isBundleHash = (h: string) => /^[0-9a-f]{64}$/.test(h);

async function fileHash(file: string): Promise<string> {
  const h = createHash("sha256");
  await pipeline(createReadStream(file), h);
  return h.digest("hex");
}

/**
 * Hash of a directory tree: relative paths, entry types, the executable bit, symlink targets and
 * file contents (not owners or times), so the same snapshot hashes the same on every node.
 */
export async function treeHash(dir: string, maxBytes = MAX_BUNDLE_BYTES): Promise<string> {
  const lines: string[] = [];
  let bytes = 0;
  const walk = async (rel: string) => {
    const entries = (await readdir(join(dir, rel))).sort();
    for (const name of entries) {
      const r = rel ? `${rel}/${name}` : name;
      const p = join(dir, r);
      const st = await lstat(p);
      if (st.isSymbolicLink()) lines.push(`l ${JSON.stringify(r)} ${await readlink(p)}`);
      else if (st.isDirectory()) {
        lines.push(`d ${JSON.stringify(r)}`);
        await walk(r);
      } else if (st.isFile()) {
        bytes += st.size;
        if (bytes > maxBytes)
          throw new Error(`bundle exceeds ${Math.round(maxBytes / 1024 ** 2)} MiB: ${dir}`);
        const x = st.mode & 0o100 ? "x" : "-";
        lines.push(`f ${JSON.stringify(r)} ${x} ${await fileHash(p)}`);
      }
    }
  };
  await walk("");
  return createHash("sha256").update(lines.join("\n")).digest("hex");
}

/** A gzip tar stream of `dir`'s contents. */
export function packBundle(dir: string): Readable {
  const child = spawn("tar", ["-czf", "-", "-C", dir, "."], { stdio: ["ignore", "pipe", "pipe"] });
  let err = "";
  child.stderr.on("data", (d: Buffer) => {
    err += d.toString();
  });
  const out = child.stdout;
  child.on("close", (code) => {
    if (code !== 0) out.destroy(new Error(`tar failed (${code}): ${err.trim()}`));
  });
  return out;
}

export const bundleDir = (root: string, hash: string) => join(root, hash);

/**
 * Unpack a tar stream into `root/<hash>` after checking that its tree hashes to `hash`. Idempotent:
 * an existing bundle is kept (a concurrent upload of the same content is not an error).
 */
export async function receiveBundle(
  root: string,
  hash: string,
  body: Readable | ReadableStream<Uint8Array>,
): Promise<string> {
  if (!isBundleHash(hash)) throw new Error(`bad bundle hash: ${hash}`);
  const dest = bundleDir(root, hash);
  if (existsSync(dest)) return dest;
  await mkdir(root, { recursive: true });
  const tmp = await mkdtemp(join(root, `.in-${hash.slice(0, 8)}-`));
  try {
    const child = spawn("tar", ["-xzf", "-", "--no-same-owner", "-C", tmp], {
      stdio: ["pipe", "ignore", "pipe"],
    });
    let err = "";
    child.stderr.on("data", (d: Buffer) => {
      err += d.toString();
    });
    const done = new Promise<number>((resolve) => child.on("close", (c) => resolve(c ?? 1)));
    const input =
      body instanceof Readable
        ? body
        : Readable.fromWeb(body as import("node:stream/web").ReadableStream);
    await pipeline(input, child.stdin).catch(() => {});
    const code = await done;
    if (code !== 0) throw new Error(`tar failed (${code}): ${err.trim()}`);
    const got = await treeHash(tmp);
    if (got !== hash) throw new Error(`bundle hash mismatch: expected ${hash}, got ${got}`);
    try {
      await rename(tmp, dest);
    } catch (e) {
      if (!existsSync(dest)) throw e;
    }
    return dest;
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
}
