import { randomUUID } from "node:crypto";
import { linkSync, readFileSync, unlinkSync, writeFileSync } from "node:fs";

interface Owner {
  pid: number;
  start: string;
  nonce: string;
}

export class ProcessLockError extends Error {}

function processStart(pid: number): string | null {
  try {
    const stat = readFileSync(`/proc/${pid}/stat`, "utf8");
    const fields = stat.slice(stat.lastIndexOf(")") + 2).split(" ");
    if (fields[0] === "Z" || fields[0] === "X") return null;
    const boot = readFileSync("/proc/sys/kernel/random/boot_id", "utf8").trim();
    return `${boot}:${fields[19]}`;
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw e;
  }
}

function readOwner(file: string): Owner | null {
  try {
    const v = JSON.parse(readFileSync(file, "utf8")) as Owner;
    if (!Number.isSafeInteger(v.pid) || v.pid <= 0 || !v.start || !v.nonce)
      throw new Error(`invalid process lock: ${file}`);
    return v;
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw e;
  }
}

/** Exclusive local process lock; a completed owner record is published atomically. */
export function acquireProcessLock(file: string): () => void {
  const start = processStart(process.pid);
  if (!start) throw new Error("cannot determine process start time");
  const owner: Owner = { pid: process.pid, start, nonce: randomUUID() };
  const candidate = `${file}.${owner.nonce}`;
  writeFileSync(candidate, JSON.stringify(owner), { flag: "wx", mode: 0o600 });
  const claim = () => {
    try {
      linkSync(candidate, file);
      return true;
    } catch (e) {
      if ((e as NodeJS.ErrnoException).code === "EEXIST") return false;
      throw e;
    }
  };
  const check = () => {
    const current = readOwner(file);
    if (current && processStart(current.pid) === current.start)
      throw new ProcessLockError(
        `${file} is held by running process PID ${current.pid} (start ${current.start})`,
      );
    return current;
  };
  try {
    if (!claim()) {
      check();
      // Serialize stale-owner removal so a contender cannot unlink a newly acquired lock.
      // This lock uses the same recovery if a previous reclaimer itself died.
      const release = acquireProcessLock(`${file}.reclaim`);
      try {
        if (check()) unlinkSync(file);
        if (!claim()) {
          const current = readOwner(file);
          throw new ProcessLockError(`${file} was acquired by process PID ${current?.pid}; retry`);
        }
      } finally {
        release();
      }
    }
  } finally {
    unlinkSync(candidate);
  }
  return () => {
    if (readOwner(file)?.nonce === owner.nonce) unlinkSync(file);
  };
}
