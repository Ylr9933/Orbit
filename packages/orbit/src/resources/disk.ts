import { statfs } from "node:fs/promises";
import { onSystemDisk } from "../config/paths.ts";
import type { DoctorCheck } from "../contracts/index.ts";

const GIB = 1024 ** 3;
/** Free space below which a disk is reported: 10% of it, but at least 50 GB and at most 500 GB. */
export const lowFreeGB = (totalGB: number) => Math.max(50, Math.min(totalGB * 0.1, 500));

/** Free space of a directory's disk, and whether it is low or the system disk. */
export async function diskCheck(name: string, dir: string, hint: string): Promise<DoctorCheck> {
  const fs = await statfs(dir).catch(() => null);
  if (!fs) return { name, ok: false, warn: false, detail: `${dir} not found` };
  const free = (fs.bavail * fs.bsize) / GIB;
  const total = (fs.blocks * fs.bsize) / GIB;
  const notes: string[] = [];
  if (onSystemDisk(dir)) notes.push(`on the system disk; ${hint}`);
  if (free < lowFreeGB(total)) notes.push("low on space");
  return {
    name,
    ok: true,
    warn: notes.length > 0,
    detail: `${dir}  ${Math.round(free)}/${Math.round(total)} GB free${notes.length ? ` (${notes.join("; ")})` : ""}`,
  };
}
