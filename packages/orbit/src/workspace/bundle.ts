// Content-addressed code bundles moved from the primary to worker nodes. A bundle is a directory
// (a code snapshot, a Dockerfile context or a method bundle) identified by the hash of its tree; a
// worker keeps each received bundle once under `cache/bundles/<hash>` and reuses it for later runs.
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { createReadStream, existsSync } from "node:fs";
import { lstat, mkdir, mkdtemp, readdir, readlink, rename, rm } from "node:fs/promises";
import { join } from "node:path";
import { PassThrough, Readable, Transform } from "node:stream";
import { pipeline } from "node:stream/promises";
import { createGunzip } from "node:zlib";

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

/**
 * A gzip tar stream of `dir`'s contents. tar's output is piped at once into the returned stream: a
 * child's stdout nobody reads yet is drained and discarded by Node when the child exits, which
 * would lose small bundles read after a delay. It ends only once tar has exited successfully.
 */
export function packBundle(dir: string): Readable {
  const child = spawn("tar", ["-czf", "-", "-C", dir, "."], { stdio: ["ignore", "pipe", "pipe"] });
  let err = "";
  child.stderr.on("data", (d: Buffer) => {
    err += d.toString();
  });
  const out = new PassThrough();
  out.on("close", () => {
    if (child.exitCode === null) child.kill("SIGKILL");
  });
  child.stdout.pipe(out, { end: false });
  child.on("error", (e) => out.destroy(e));
  child.on("close", (code) => {
    if (code === 0) out.end();
    else out.destroy(new Error(`tar failed (${code}): ${err.trim()}`));
  });
  return out;
}

export const bundleDir = (root: string, hash: string) => join(root, hash);

function byteLimit(maxBytes: number, kind: string): Transform {
  let bytes = 0;
  return new Transform({
    transform(chunk: Buffer, _encoding, done) {
      bytes += chunk.length;
      done(bytes > maxBytes ? new Error(`${kind} bundle exceeds ${maxBytes} bytes`) : null, chunk);
    },
  });
}

/**
 * Unpack a tar stream into `root/<hash>` after checking that its tree hashes to `hash`. Idempotent:
 * an existing bundle is kept (a concurrent upload of the same content is not an error).
 */
export async function receiveBundle(
  root: string,
  hash: string,
  body: Readable | ReadableStream<Uint8Array>,
  maxBytes = MAX_BUNDLE_BYTES,
): Promise<string> {
  if (!isBundleHash(hash)) throw new Error(`bad bundle hash: ${hash}`);
  const dest = bundleDir(root, hash);
  if (existsSync(dest)) return dest;
  await mkdir(root, { recursive: true, mode: 0o700 });
  const tmp = await mkdtemp(join(root, `.in-${hash.slice(0, 8)}-`));
  try {
    // Drain archive padding to EOF before tar closes the upload pipeline's stdin.
    const child = spawn("tar", ["-xf", "-", "--ignore-zeros", "--no-same-owner", "-C", tmp], {
      stdio: ["pipe", "ignore", "pipe"],
    });
    let err = "";
    child.stderr.on("data", (d: Buffer) => {
      err = (err + d.toString()).slice(-16_384);
    });
    const done = new Promise<number>((resolve, reject) => {
      child.on("error", reject);
      child.on("close", (c) => resolve(c ?? 1));
    });
    const input =
      body instanceof Readable
        ? body
        : Readable.fromWeb(body as import("node:stream/web").ReadableStream);
    try {
      await Promise.all([
        pipeline(
          input,
          byteLimit(maxBytes, "compressed"),
          createGunzip(),
          byteLimit(maxBytes, "unpacked"),
          child.stdin,
        ),
        done.then((code) => {
          if (code !== 0) throw new Error(`tar failed (${code}): ${err.trim()}`);
        }),
      ]);
    } catch (e) {
      input.destroy();
      child.kill("SIGKILL");
      await done.catch(() => {});
      throw e;
    }
    const got = await treeHash(tmp, maxBytes);
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
